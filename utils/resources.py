import os
import sys

def get_base_path():
    """获取程序运行的基础路径（兼容 PyInstaller 打包环境）"""
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        # PyInstaller 打包后的临时目录 (onefile) 或 _internal (onedir)
        return sys._MEIPASS
    else:
        # 开发环境
        # utils/__init__.py 的上两级目录 (live2d-self-v2/utils/.. -> live2d-self-v2)
        return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

CURRENT_DIRECTORY = get_base_path()

def get_env_path():
    env_name = ".env"

    # 1. 检查 EXE 所在目录 (用户可能手动放了 .env)
    if getattr(sys, 'frozen', False):
        exe_dir = os.path.dirname(sys.executable)
        exe_env = os.path.join(exe_dir, env_name)
        if os.path.exists(exe_env):
            return exe_env

    # 2. 检查 _internal / _MEIPASS 目录 (打包进去的 .env)
    internal_env = os.path.join(CURRENT_DIRECTORY, env_name)
    if os.path.exists(internal_env):
        return internal_env

    # 3. 开发环境根目录
    dev_env = os.path.join(CURRENT_DIRECTORY, env_name)
    if os.path.exists(dev_env):
        return dev_env

    return None

ENV_PATH = get_env_path()

# 优先检查 CURRENT_DIRECTORY/resources
RESOURCES_DIRECTORY = os.path.join(CURRENT_DIRECTORY, "resources")

# 如果没找到，尝试检查 exe 所在目录 (onedir 模式下有时资源会放在 exe 旁边)
if getattr(sys, 'frozen', False) and not os.path.exists(RESOURCES_DIRECTORY):
    exe_dir = os.path.dirname(sys.executable)
    alt_res_dir = os.path.join(exe_dir, "resources")
    if os.path.exists(alt_res_dir):
        RESOURCES_DIRECTORY = alt_res_dir
