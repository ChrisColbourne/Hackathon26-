// board_prep: OpenCV preprocessing for the whiteboard camera, exposed to Python.
//
//   find_board(frame)            -> [(x,y)×4] corners TL,TR,BR,BL, or None
//   warp(frame, quad, w, h)      -> flat top-down image of the board
//   enhance(flat)                -> contrast-boosted copy (marker ink pops)
//   change_score(gray_a, gray_b) -> fraction of pixels that changed, 0..1
//   prepare(frame, w, h)         -> (flat_bgr, found)
//
// Arrays are numpy uint8, HxW (gray) or HxWx3 (BGR, as OpenCV gives them).
// brain/vision/__init__.py falls back to vision_py.py if this isn't built.

#include <pybind11/numpy.h>
#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include <opencv2/opencv.hpp>

#include <algorithm>
#include <cstring>
#include <optional>
#include <stdexcept>
#include <vector>

namespace py = pybind11;

using Arr = py::array_t<uint8_t, py::array::c_style | py::array::forcecast>;
using Quad = std::vector<std::pair<float, float>>;

// View a numpy array as a cv::Mat without copying. Valid only while `a` lives.
static cv::Mat as_mat(const Arr& a) {
    py::buffer_info info = a.request();
    if (info.ndim == 2)
        return cv::Mat((int)info.shape[0], (int)info.shape[1], CV_8UC1, info.ptr);
    if (info.ndim == 3 && info.shape[2] == 3)
        return cv::Mat((int)info.shape[0], (int)info.shape[1], CV_8UC3, info.ptr);
    throw std::invalid_argument("expected a uint8 array of shape HxW or HxWx3");
}

static py::array_t<uint8_t> to_array(const cv::Mat& m_in) {
    cv::Mat m = m_in.isContinuous() ? m_in : m_in.clone();
    std::vector<py::ssize_t> shape{m.rows, m.cols};
    if (m.channels() > 1) shape.push_back(m.channels());
    py::array_t<uint8_t> out(shape);
    std::memcpy(out.mutable_data(), m.data, m.total() * m.elemSize());
    return out;
}

// Order corners as TL, TR, BR, BL so the warp always comes out upright.
static Quad order_corners(const std::vector<cv::Point>& pts) {
    auto sum = [](const cv::Point& p) { return p.x + p.y; };
    auto diff = [](const cv::Point& p) { return p.y - p.x; };
    cv::Point tl = *std::min_element(pts.begin(), pts.end(), [&](auto& a, auto& b) { return sum(a) < sum(b); });
    cv::Point br = *std::max_element(pts.begin(), pts.end(), [&](auto& a, auto& b) { return sum(a) < sum(b); });
    cv::Point tr = *std::min_element(pts.begin(), pts.end(), [&](auto& a, auto& b) { return diff(a) < diff(b); });
    cv::Point bl = *std::max_element(pts.begin(), pts.end(), [&](auto& a, auto& b) { return diff(a) < diff(b); });
    return {{(float)tl.x, (float)tl.y}, {(float)tr.x, (float)tr.y}, {(float)br.x, (float)br.y}, {(float)bl.x, (float)bl.y}};
}

// Largest convex quadrilateral covering at least `min_area_frac` of the frame.
static std::optional<Quad> find_board_impl(const cv::Mat& frame, double min_area_frac) {
    cv::Mat gray, edges;
    if (frame.channels() == 3) cv::cvtColor(frame, gray, cv::COLOR_BGR2GRAY); else gray = frame;
    cv::GaussianBlur(gray, gray, cv::Size(5, 5), 0);
    cv::Canny(gray, edges, 50, 150);
    cv::dilate(edges, edges, cv::Mat(), cv::Point(-1, -1), 1);

    std::vector<std::vector<cv::Point>> contours;
    cv::findContours(edges, contours, cv::RETR_EXTERNAL, cv::CHAIN_APPROX_SIMPLE);
    std::sort(contours.begin(), contours.end(),
              [](auto& a, auto& b) { return cv::contourArea(a) > cv::contourArea(b); });

    const double min_area = min_area_frac * frame.rows * frame.cols;
    for (const auto& c : contours) {
        if (cv::contourArea(c) < min_area) break;
        std::vector<cv::Point> approx;
        cv::approxPolyDP(c, approx, 0.02 * cv::arcLength(c, true), true);
        if (approx.size() == 4 && cv::isContourConvex(approx)) return order_corners(approx);
    }
    return std::nullopt;
}

static cv::Mat warp_impl(const cv::Mat& frame, const Quad& quad, int w, int h) {
    if (quad.size() != 4) throw std::invalid_argument("quad must have 4 corners");
    std::vector<cv::Point2f> src, dst{{0, 0}, {(float)w - 1, 0}, {(float)w - 1, (float)h - 1}, {0, (float)h - 1}};
    for (auto& p : quad) src.emplace_back(p.first, p.second);
    cv::Mat M = cv::getPerspectiveTransform(src, dst), out;
    cv::warpPerspective(frame, out, M, cv::Size(w, h), cv::INTER_LINEAR, cv::BORDER_REPLICATE);
    return out;
}

// CLAHE on the lightness channel: marker ink gets darker, glare gets flatter,
// colours (red/blue markers) are preserved.
static cv::Mat enhance_impl(const cv::Mat& bgr) {
    if (bgr.channels() != 3) return bgr.clone();
    cv::Mat lab, out;
    cv::cvtColor(bgr, lab, cv::COLOR_BGR2Lab);
    std::vector<cv::Mat> ch;
    cv::split(lab, ch);
    cv::createCLAHE(2.0, cv::Size(8, 8))->apply(ch[0], ch[0]);
    cv::merge(ch, lab);
    cv::cvtColor(lab, out, cv::COLOR_Lab2BGR);
    return out;
}

// Fraction of pixels whose brightness moved by more than `thresh`, after
// shrinking both images to the same small size and blurring away noise.
static double change_score_impl(const cv::Mat& a_in, const cv::Mat& b_in, int thresh) {
    const cv::Size small(320, 180);
    cv::Mat a, b;
    if (a_in.channels() == 3) cv::cvtColor(a_in, a, cv::COLOR_BGR2GRAY); else a = a_in;
    if (b_in.channels() == 3) cv::cvtColor(b_in, b, cv::COLOR_BGR2GRAY); else b = b_in;
    cv::resize(a, a, small, 0, 0, cv::INTER_AREA);
    cv::resize(b, b, small, 0, 0, cv::INTER_AREA);
    cv::GaussianBlur(a, a, cv::Size(5, 5), 0);
    cv::GaussianBlur(b, b, cv::Size(5, 5), 0);
    cv::Mat d;
    cv::absdiff(a, b, d);
    cv::threshold(d, d, thresh, 255, cv::THRESH_BINARY);
    return (double)cv::countNonZero(d) / (double)d.total();
}

// ---- bindings --------------------------------------------------------------

static std::optional<Quad> find_board(const Arr& frame, double min_area_frac) {
    return find_board_impl(as_mat(frame), min_area_frac);
}

static py::array_t<uint8_t> warp(const Arr& frame, const Quad& quad, int w, int h) {
    return to_array(warp_impl(as_mat(frame), quad, w, h));
}

static py::array_t<uint8_t> enhance(const Arr& flat) { return to_array(enhance_impl(as_mat(flat))); }

static double change_score(const Arr& a, const Arr& b, int thresh) {
    return change_score_impl(as_mat(a), as_mat(b), thresh);
}

// One-stop: crop + deskew if the board is found, else shrink the raw frame.
static py::tuple prepare(const Arr& frame, int w, int h, double min_area_frac) {
    cv::Mat f = as_mat(frame);
    if (auto q = find_board_impl(f, min_area_frac)) return py::make_tuple(to_array(warp_impl(f, *q, w, h)), true);
    cv::Mat small;
    double s = std::min(1.0, (double)w / f.cols);
    cv::resize(f, small, cv::Size(), s, s, cv::INTER_AREA);
    return py::make_tuple(to_array(small), false);
}

PYBIND11_MODULE(board_prep, m) {
    m.doc() = "Whiteboard preprocessing (OpenCV, C++)";
    m.def("find_board", &find_board, py::arg("frame"), py::arg("min_area_frac") = 0.2);
    m.def("warp", &warp, py::arg("frame"), py::arg("quad"), py::arg("w") = 1280, py::arg("h") = 720);
    m.def("enhance", &enhance, py::arg("flat"));
    m.def("change_score", &change_score, py::arg("a"), py::arg("b"), py::arg("thresh") = 30);
    m.def("prepare", &prepare, py::arg("frame"), py::arg("w") = 1280, py::arg("h") = 720,
          py::arg("min_area_frac") = 0.2);
    m.attr("BACKEND") = "cpp";
}
