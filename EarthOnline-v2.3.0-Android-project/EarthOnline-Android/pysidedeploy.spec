[app]
title = Earth Online
project_dir = .
input_file = main.py
exec_directory = .
project_file = EarthOnlineMobile.pyproject
icon =

[python]
python_path =
packages =
android_packages = buildozer==1.5.0,cython==0.29.33

[qt]
qml_files =
excluded_qml_plugins =
modules = Core,Gui,Widgets
plugins =

[android]
wheel_pyside =
wheel_shiboken =
plugins = platforms,styles,imageformats

[nuitka]
macos.permissions =
mode = onefile
extra_args = --quiet --noinclude-qt-translations

[buildozer]
mode = debug
recipe_dir =
jars_dir =
ndk_path =
sdk_path =
local_libs =
arch = aarch64
