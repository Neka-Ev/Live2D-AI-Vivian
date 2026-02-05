import os
import json
from utils.logger_setup import get_logger

logger = get_logger("ModelHelper")

class ModelConfigParser:
    def __init__(self):
        self.data = {}

    def load_config(self, model_json_path: str):
        self.data = {}
        if not os.path.exists(model_json_path):
             logger.error(f"Json path not found: {model_json_path}")
             return

        try:
            with open(model_json_path, 'r', encoding='utf-8') as f:
                self.data = json.load(f)
        except Exception as e:
            logger.error(f"Failed to load model json: {e}")

    def get_motion_text(self, group_name: str, index: int) -> str:
        try:
            # Structure: FileReferences -> Motions -> GroupName -> [Array] -> Item -> Text
            motions = self.data.get("FileReferences", {}).get("Motions", {})
            group = motions.get(group_name, [])
            if group and 0 <= index < len(group):
                return group[index].get("Text", "")
        except Exception as e:
            logger.error(f"Error getting motion text: {e}")
        return ""

class ModelAttribute:
    def __init__(self, scale: float , positionOffset: tuple[float, float], lipParamY: float = 0.0):
        self.scale = scale
        self.positionOffset = positionOffset
        self.lipParamY = lipParamY

    def getNowScale(self) -> float:
        return self.scale

    def getNowPositionOffset(self) -> tuple[float, float]:
        return self.positionOffset

    def getLipParamY(self) -> float:
        return self.lipParamY

    def setNewScale(self, scale: float):
        self.scale = scale

    def setNewPositionOffset(self, positionOffset: tuple[float, float]):
        self.positionOffset = positionOffset

    def setLipParamY(self, lipParamY: float):
        self.lipParamY = lipParamY


class ModelHitManager:
    def __init__(self):
        self.area_mapping = {
            "Face": {
                "Part14", "Part17", "Part29", "Part30",  # 脸, 脸框, 五官, 耳朵
                "Part2", "Part3", "Part4", "Part11", "Part12", "Part28",  # 眉毛相关
                "Part18", "Part19", "Part20", "Part21", "Part22", "Part23", "Part73", "Part71",  # 眼睛相关
                "Part24", "Part25", "Part26", "Part27", "Part72",  # 鼻子, 嘴巴
                "Part15", "Part16", "Part70"  # 情绪, 额外部件
            },
            "Head": {
                "Part6", "Part7", "Part8", "Part9", "Part10",  # 前发, 呆毛, 刘海, 侧发
                "Part13", "Part54", "Part55", "Part56", "Part59", "Part60",  # 头发阴影, 后发, 碎发
                "Part62", "Part63", "Part64", "Part65", "Part66", "Part68"  # 这些是伞的蝴蝶结
            },
            "Hand": {
                "Part42", "Part43", "Part53",  # 右臂, 手
                "Part48",  # 撑伞手
            },
            "Accessories":{
                "Part31", "Part5", "Part34",  "Part37" # 领饰, 胸前蝴蝶结, 透明纱
            },
            "Breast": {
              "Part36" # 基本就过滤为胸部了
            },
            "Body": {
                "Part32", "Part44", "Part57", "Part58", # 身体
                "Part51", "Part52", # 手臂
                "Part33", "Part40", "Part35", # 衣领, 腰部
                "Part41",  # 裙边
                "Part38", "Part39", # 腰部+裙边
            },
            "Leg": {
                "Part45", "Part46",  # 腿
            }
        }
        self.exp_mapping={
            "shy":{
                "Face", "Breast", "Leg"
            },
            "umbrella_close":{
                "Hand", "Head"
            },
            "scowl":{
                # 暂留
            },
            "normal":{
                 "Accessories", "Body"
            }
        }

        self.priority_list = ["Hand", "Accessories", "Head", "Face", "Leg", "Breast", "Body"]

    def get_hit_feedback(self, hit_part_ids: list[str]):
        """
        根据点击返回的多个部件ID，判断最终的逻辑区域并确定对应的表情
        :param hit_part_ids: Live2D SDK 返回的点击命中的 ID 列表
        :return: 区域名称 (例如 "Face") 或 None，以及对应的表情名称 (例如 "shy")
        """
        expression = "normal"
        area_name = None
        if not hit_part_ids:
            return area_name, expression  # 未命中任何部件
        # 将输入的列表转换为集合，提高查找效率
        hit_set = set(hit_part_ids)
        # 按照优先级遍历区域
        for area_name in self.priority_list:
            target_parts = self.area_mapping[area_name]

            # 使用集合求交集：如果命中的部件里有属于当前区域的
            if not hit_set.isdisjoint(target_parts):
                for exp_name, affected_areas in self.exp_mapping.items():
                    if area_name in affected_areas: # 检查该区域对应表情
                        expression = exp_name
                return area_name, expression  # 返回对应表情

        return area_name, expression  # 未命中定义区域
