cmake_minimum_required(VERSION 3.15)
project(board_prep LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
if(NOT CMAKE_BUILD_TYPE)
  set(CMAKE_BUILD_TYPE Release)
endif()

find_package(OpenCV REQUIRED)

# build.sh passes -Dpybind11_DIR. Without it (VS Code's CMake Tools, a bare
# `cmake -S . -B build`), ask the project venv's pybind11 where its CMake files
# are, and build against that same Python so the module's suffix matches.
if(NOT pybind11_DIR)
  set(_venv_py "${CMAKE_CURRENT_SOURCE_DIR}/../../.venv/bin/python")
  if(NOT PYTHON_EXECUTABLE AND EXISTS "${_venv_py}")
    set(PYTHON_EXECUTABLE "${_venv_py}" CACHE FILEPATH "Python to build against" FORCE)
    set(Python_EXECUTABLE "${_venv_py}" CACHE FILEPATH "Python to build against" FORCE)
  endif()
  if(PYTHON_EXECUTABLE)
    set(_py "${PYTHON_EXECUTABLE}")
  else()
    find_package(Python3 COMPONENTS Interpreter REQUIRED)
    set(_py "${Python3_EXECUTABLE}")
  endif()
  execute_process(
    COMMAND "${_py}" -c "import pybind11; print(pybind11.get_cmake_dir())"
    OUTPUT_VARIABLE _pybind11_dir OUTPUT_STRIP_TRAILING_WHITESPACE
    RESULT_VARIABLE _rc ERROR_QUIET)
  if(NOT _rc EQUAL 0)
    message(FATAL_ERROR "pybind11 not found for ${_py}. Run: pip install -r brain/requirements.txt")
  endif()
  # FORCE: a failed earlier configure caches pybind11_DIR-NOTFOUND.
  set(pybind11_DIR "${_pybind11_dir}" CACHE PATH "pybind11 CMake config dir" FORCE)
endif()
find_package(pybind11 CONFIG REQUIRED)

pybind11_add_module(board_prep board_prep.cpp)
target_include_directories(board_prep PRIVATE ${OpenCV_INCLUDE_DIRS})
target_link_libraries(board_prep PRIVATE ${OpenCV_LIBS})

# build.sh copies the finished module next to __init__.py. (We don't set
# LIBRARY_OUTPUT_DIRECTORY to the source dir: an apostrophe in the project path
# breaks the generated link command.)
