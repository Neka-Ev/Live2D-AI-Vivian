import sys
import os
import traceback
from PyQt5.QtWidgets import QApplication, QMessageBox
from PyQt5.QtGui import QIcon
from PyQt5.QtCore import Qt
import live2d.v3 as live2d
from mainwindow import MainWindow
from utils.resources import RESOURCES_DIRECTORY, ENV_PATH # Import ENV_PATH
from dotenv import load_dotenv # Import load_dotenv

# App入口

def exception_hook(exctype, value, tb):
    """全局异常捕获"""
    error_msg = "".join(traceback.format_exception(exctype, value, tb))
    print(error_msg)

    # 尝试写入日志文件
    try:
        with open("crash.log", "w", encoding="utf-8") as f:
            f.write(error_msg)
    except:
        pass

    # 确保应用已经创建才能弹窗
    if QApplication.instance():
        msg_box = QMessageBox()
        msg_box.setIcon(QMessageBox.Critical)
        msg_box.setText("程序发生严重错误")
        msg_box.setInformativeText(str(value))
        msg_box.setDetailedText(error_msg)
        msg_box.setWindowTitle("Error")
        msg_box.exec_()

    sys.__excepthook__(exctype, value, tb)

def main():
    sys.excepthook = exception_hook

    # Load environment variables explicitly
    if ENV_PATH:
        print(f"Loading .env from: {ENV_PATH}")
        load_dotenv(ENV_PATH)
    else:
        print("Warning: .env file not found!")

    # live2d init might fail if dll missing
    try:
        live2d.init()
    except Exception as e:
        print(f"Failed to init Live2D: {e}")
        # Let the hook catch it or handle gracefully
        raise e

    # 启用高 DPI 缩放
    if hasattr(Qt, 'AA_EnableHighDpiScaling'):
        QApplication.setAttribute(Qt.AA_EnableHighDpiScaling)
    if hasattr(Qt, 'AA_UseHighDpiPixmaps'):
        QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps)

    # 设置缩放策略为 PassThrough，防止 150% (1.5) 被上取为 200% (2.0)
    if hasattr(Qt, 'HighDpiScaleFactorRoundingPolicy'):
        QApplication.setHighDpiScaleFactorRoundingPolicy(
            Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)

    app = QApplication(sys.argv)

    # 设置应用图标 (任务栏图标)
    icon_path = os.path.join(RESOURCES_DIRECTORY, "icons/icon.png")
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))

    main_window = MainWindow()
    main_window.show()

    try:
        app.exec()
    finally:
        live2d.dispose()


if __name__ == "__main__":
    main()
