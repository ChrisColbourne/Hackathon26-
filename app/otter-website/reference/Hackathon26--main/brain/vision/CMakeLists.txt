cmake_minimum_required(VERSION 3.15)
project(board_prep LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
if(NOT CMAKE_BUILD_TYPE)
  set(CMAKE_BUILD_TYPE Release)
endif()

find_package(OpenCV REQUIRED)
find_package(pybind11 CONFIG REQUIRED)   # pass -Dpybind11_DIR=$(python -m pybind11 --cmakedir)

pybind11_add_module(board_prep board_prep.cpp)
target_include_directories(board_prep PRIVATE ${OpenCV_INCLUDE_DIRS})
target_link_libraries(board_prep PRIVATE ${OpenCV_LIBS})

# build.sh copies the finished module next to __init__.py. (We don't set
# LIBRARY_OUTPUT_DIRECTORY to the source dir: an apostrophe in the project path
# breaks the generated link command.)
