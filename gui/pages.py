# -*- coding: utf-8 -*-
"""各功能页签"""

import re

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QAction, QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QCheckBox, QTableWidget, QTableWidgetItem, QInputDialog, QMessageBox, QMenu,
    QDialog, QFormLayout, QComboBox, QDialogButtonBox, QPlainTextEdit,
    QAbstractItemView, QSpinBox, QFrame,
)

from gui.theme import make_table


ELEMENTARY_TYPES = {"int", "float", "bool", "str", "None"}

# 变量名 / 字段名关键词 → 游戏里常见的中文叫法。
# 英文为主，同时收西班牙语（不少欧美 SLG 原文是西语），提高自动适配命中率。
ATTR_CN_LABELS = {
    # ---- 金钱 / 资源 ----
    "money": "金钱", "cash": "现金", "coin": "硬币", "coins": "硬币",
    "gold": "金币", "goldcoin": "金币", "goldcoins": "金币",
    "credit": "信用点", "credits": "信用点", "funds": "资金",
    "currency": "货币", "dollar": "美元", "dollars": "美元",
    "euro": "欧元", "euros": "欧元", "yen": "日元",
    "diamond": "钻石", "diamonds": "钻石", "gem": "宝石", "gems": "宝石",
    "crystal": "水晶", "crystals": "水晶", "jewel": "珠宝", "jewels": "珠宝",
    "ticket": "票券", "tickets": "票券", "token": "代币", "tokens": "代币",
    "coupon": "优惠券", "voucher": "兑换券", "key": "钥匙", "keys": "钥匙",
    "energy": "体力", "stamina": "体力", "hp": "生命", "health": "生命",
    "mp": "魔力", "mana": "魔力", "ammo": "弹药", "bullet": "子弹",
    "bullets": "子弹", "food": "食物", "water": "水", "supplies": "补给",
    "fuel": "燃油", "gas": "汽油", "scrap": "废料", "wood": "木材",
    "stone": "石头", "iron": "铁", "ore": "矿石", "herb": "草药",
    "potions": "药水", "potion": "药水", "seed": "种子", "seeds": "种子",
    "crop": "作物", "crops": "作物", "cloth": "布料", "fabric": "布料",
    "leather": "皮革", "material": "材料", "materials": "材料",
    "ingredient": "食材", "ingredients": "食材", "resource": "资源",
    "resources": "资源", "repair": "修理材料", "medkit": "医疗包",
    # 西语资源
    "dinero": "金钱", "plata": "金钱", "oro": "金币", "moneda": "硬币",
    "monedas": "硬币", "energia": "体力", "salud": "生命", "vida": "生命",
    "balas": "子弹", "municion": "弹药", "combustible": "燃油",
    "suministros": "补给", "recursos": "资源", "materiales": "材料",
    "gemas": "宝石", "diamantes": "钻石", "cristales": "水晶",
    "entradas": "票券", "fichas": "代币", "puntos": "点数",
    "comida": "食物", "agua": "水", "llave": "钥匙", "llaves": "钥匙",

    # ---- 好感 / 关系 ----
    "affection": "好感", "affinity": "好感", "fondness": "好感",
    "favor": "好感", "favour": "好感", "likes": "好感", "like": "好感",
    "love": "爱意", "loves": "爱意", "romance": "恋情",
    "relationship": "关系", "relation": "关系", "relations": "关系",
    "trust": "信任", "heart": "好感", "hearts": "好感",
    "intimacy": "亲密", "bond": "羁绊", "charm": "魅力",
    "attraction": "吸引力", "desire": "欲望", "lust": "欲望",
    "passion": "热情", "friend": "友情", "friendship": "友情",
    "respect": "尊敬", "attitude": "态度", "opinion": "看法",
    "opinions": "看法", "allure": "魅力", "appeal": "吸引力",
    "interest": "兴趣", "interests": "兴趣", "view": "看法",
    "views": "看法", "looks": "外貌", "conflict": "冲突",
    "state": "状态", "known": "已认识", "firstmetdate": "初次见面",
    # 西语
    "amor": "爱意", "afecto": "好感", "confianza": "信任",
    "relacion": "关系", "pasion": "热情", "deseo": "欲望",
    "lujuria": "欲望", "corazon": "好感", "carino": "好感",
    "atraccion": "吸引力", "amistad": "友情", "respeto": "尊敬",

    # ---- 角色状态 ----
    "corruption": "堕落", "obedience": "服从", "submission": "顺从",
    "mood": "心情", "sanity": "理智", "stress": "压力",
    "fatigue": "疲劳", "tiredness": "疲劳", "drunk": "醉酒",
    "alcohol": "酒精", "pregnancy": "怀孕", "horny": "欲火",
    "arousal": "兴奋", "anger": "愤怒", "fear": "恐惧",
    "shyness": "害羞", "shame": "羞耻", "willpower": "意志",
    "discipline": "纪律", "training": "训练", "addiction": "成瘾",
    "dependency": "依赖", "grades": "成绩", "popularity": "人气",
    "influence": "影响力", "hygiene": "清洁", "cleanliness": "清洁",
    "fitness": "体质", "beauty": "美貌", "dominance": "支配",
    "sensitivity": "敏感", "pleasure": "快感", "pain": "疼痛",
    "hunger": "饥饿", "thirst": "口渴", "suspicion": "怀疑",
    "jealousy": "嫉妒", "happiness": "幸福", "depression": "抑郁",
    "confidence": "自信", "courage": "勇气", "pride": "自尊",
    # 西语
    "corrupcion": "堕落", "obediencia": "服从", "sumision": "顺从",
    "humor": "心情", "cordura": "理智", "estres": "压力",
    "fatiga": "疲劳", "embarazo": "怀孕", "excitacion": "兴奋",
    "ira": "愤怒", "miedo": "恐惧", "verguenza": "羞耻",
    "voluntad": "意志", "disciplina": "纪律", "entrenamiento": "训练",
    "adiccion": "成瘾", "popularidad": "人气", "influencia": "影响力",
    "higiene": "清洁", "belleza": "美貌", "sensibilidad": "敏感",
    "dolor": "疼痛", "hambre": "饥饿", "sed": "口渴",
    "sospecha": "怀疑", "celos": "嫉妒", "felicidad": "幸福",
    "valor": "勇气", "orgullo": "自尊",

    # ---- 等级 / 成长 ----
    "level": "等级", "lvl": "等级", "exp": "经验", "xp": "经验",
    "experience": "经验", "point": "点数", "points": "点数",
    "stat": "属性", "stats": "属性", "skill": "技能", "skills": "技能",
    "proficiency": "熟练度", "progress": "进度", "rank": "排名",
    "score": "分数", "reputation": "声望", "fame": "名气",
    "karma": "善恶值", "intelligence": "智力", "strength": "力量",
    "agility": "敏捷", "charisma": "魅力", "luck": "幸运",
    "wisdom": "智慧", "perk": "特长", "perks": "特长", "talent": "天赋",
    "defense": "防御", "attack": "攻击", "speed": "速度",
    "dexterity": "灵巧", "endurance": "耐力", "vitality": "活力",
    "magic": "魔力", "power": "战力", "combo": "连击",
    # 西语
    "nivel": "等级", "experiencia": "经验", "habilidad": "技能",
    "habilidades": "技能", "progreso": "进度", "rango": "排名",
    "puntuacion": "分数", "reputacion": "声望", "fama": "名气",
    "inteligencia": "智力", "fuerza": "力量", "agilidad": "敏捷",
    "carisma": "魅力", "suerte": "幸运", "sabiduria": "智慧",
    "talento": "天赋", "defensa": "防御", "ataque": "攻击",
    "velocidad": "速度", "resistencia": "耐力", "vitalidad": "活力",
    "magia": "魔力", "poder": "战力",

    # ---- 存档 / 流程 / 通用字段 ----
    "age": "年龄", "day": "天数", "days": "天数", "week": "周",
    "month": "月", "year": "年", "hour": "小时", "time": "时间",
    "quest": "任务", "quests": "任务", "chapter": "章节",
    "stage": "阶段", "phase": "阶段", "scene": "场景",
    "room": "房间", "rooms": "房间", "roomwt": "房间权重",
    "room_wt": "房间权重", "room_r": "房间记录", "room_f": "房间标记",
    "rate": "率", "rating": "评级", "firstquest": "首个任务",
    "displayorder": "排序", "order": "顺序", "sort": "排序",
    "change": "变化", "delta": "变化", "test": "测试",
    "debug": "调试", "count": "数量", "amount": "数量",
    "num": "数量", "qty": "数量", "quantity": "数量",
    "number": "数量", "total": "累计", "value": "值",
    "flag": "标记", "flags": "标记", "unlocked": "已解锁",
    "unlock": "解锁", "seen": "已看过", "visited": "已访问",
    "completed": "已完成", "done": "已完成", "active": "启用",
    "enabled": "启用", "opened": "已开启", "bought": "已购买",
    "sold": "已出售", "owned": "拥有", "equipped": "已装备",
    "weight": "重量", "durability": "耐久", "quality": "品质",
    "price": "价格", "cost": "花费", "slot": "槽位",
    "slots": "槽位", "capacity": "容量", "maxslot": "最大槽位",
    "size": "尺寸", "gender": "性别", "name": "名称",

    # ---- 对象 / 记录通用字段 ----
    "object": "对象", "obj": "对象", "field": "字段", "attr": "属性",
    "data": "数据", "item": "物品", "items": "物品", "entry": "条目",
    "list": "列表", "array": "数组", "map": "映射", "table": "表",
    "id": "编号", "index": "序号", "key": "键", "keys": "键",
    "type": "类型", "kind": "类别", "class": "类", "group": "分组",
    "groups": "分组", "category": "分类", "section": "分区",
    "label": "标签", "title": "标题", "description": "描述",
    "desc": "描述", "text": "文本", "string": "字符串", "str": "字符串",
    "icon": "图标", "image": "图片", "images": "图片", "img": "图片",
    "bkg_img": "背景图", "hover_bkg_img": "悬停背景图",
    "sub_imgs": "子图", "pict": "图片", "photo": "照片",
    "photos": "照片", "contactphoto": "联系人照片",
    "contactphotos": "联系人照片", "parent": "父级", "child": "子级",
    "children": "子级", "default": "默认", "set": "集合",
    "returnable": "可返回", "event": "事件", "events": "事件",
    "height": "高度", "width": "宽度", "position": "位置", "pos": "位置",
    "notes": "备注", "note": "备注", "comment": "注释",
    "hint": "提示", "hints": "提示", "hintzone": "提示区域",
    "condition": "条件", "conditions": "条件", "priority": "优先级",
    "prioritylevel": "优先级", "parentpriority": "父级优先级",
    "probability": "概率", "randoms": "随机项", "ladder": "阶梯",
    "callbacks": "回调", "callback": "回调", "args": "参数",
    "kwargs": "关键字参数", "exclude": "排除", "include": "包含",
    "additionals": "附加项", "additional": "附加项", "extra": "额外",
    "tags": "标签", "tag": "标签", "tmptags": "临时标签",
    "elem": "元素", "elems": "元素", "part": "部位", "parts": "部位",
    "zone": "区域", "zones": "区域", "participant": "参与者",
    "participants": "参与者", "activated": "已激活",
    "activated_participants": "已激活参与者",
    "selectable": "可选择", "selected": "已选中", "selitem": "选中物品",
    "border": "边框", "solidstates": "固定状态", "stdshift": "标准偏移",
    "weekdays": "星期", "weekday": "星期几", "family": "家庭",
    "family_status": "家庭状况",
    "standard": "标准", "std": "标准",
    "version": "版本", "oldversion": "旧版本", "length": "长度",
    "week": "周",

    # ---- 界面 / 显示字段 ----
    "show": "显示", "showenergy": "显示体力", "showdate": "显示日期",
    "showtime": "显示时间", "showlocation": "显示地点",
    "showallure": "显示魅力", "showmoney": "显示金钱",
    "displayorder": "排序", "menutheme": "菜单主题", "curmenu": "当前菜单",
    "sidescreens": "侧边界面", "timestring": "时间文本",
    "datestring": "日期文本", "browse_site_page": "浏览网站页面",
    "browsesitepage": "浏览网站页面", "defaultplaces": "默认地点",
    "dayplan": "日程计划", "lastdayplan": "上次日程",
    "daydevoirs": "每日任务", "eventsqueue": "事件队列",
    "plannedevents": "计划事件", "gatherstats": "收集统计",
    "travelcallbacks": "旅行回调", "searchthemes": "搜索主题",
    "interestthemes": "兴趣主题", "talkthemes": "对话主题",
    "locationslist": "地点列表", "personslist": "角色列表",
    "itemslist": "物品列表", "questslist": "任务列表",
    "scenes": "场景", "menu": "菜单", "screen": "界面",
    "screens": "界面", "button": "按钮", "window": "窗口",

    # ---- 角色 / 关系（本作 PersonClass / RelationClass）----
    "alias": "别名", "alias_std": "标准别名", "aliasstd": "标准别名",
    "aliasstandard": "标准别名",
    "fullname": "全名", "full_name": "全名", "diminutive": "昵称",
    "spoken": "称呼", "behaviors": "行为", "behavior": "行为",
    "dynamicvars": "动态变量", "dynamic_vars": "动态变量",
    "interests": "兴趣", "interest": "兴趣", "interestsused": "已用兴趣",
    "interestsreaction": "兴趣反应", "interestsballance": "兴趣平衡",
    "interesthintcounter": "兴趣提示计数",
    "relationshintcounter": "关系提示计数",
    "rel": "关系", "rels": "关系", "relationlist": "关系表",
    "sub1": "对象1", "sub2": "对象2", "sub1notes": "对象1备注",
    "sub2notes": "对象2备注", "harem_part": "后宫部分",
    "haremart": "后宫部分", "is_sleeping_date": "睡眠日期",
    "messages": "消息", "message": "消息", "temp": "临时",
    "cur": "当前", "curposition": "当前位置", "positionname": "位置名称",
    "positiontext": "职位文本", "curobject": "当前对象",
    "curobjectname": "当前对象名称", "objname": "对象名称",
    "curstep": "当前步骤", "lastchanges": "上次变化",
    "currandnumb": "当前随机数", "randmaxnumb": "随机上限",
    "curearn": "当前收入", "towork": "工作次数",
    "lefttowork": "剩余工作", "left": "剩余", "timetable": "时间表",
    "locations_time_map": "地点时间表",
    "locationstimemap": "地点时间表",
    "checked_time_map": "已检查时间表", "checkedtimemap": "已检查时间表",
    "prevent_roll_back": "禁止回退", "preventrollback": "禁止回退",
    "prev_activated_tm": "上次激活时间", "prevactivatedtm": "上次激活时间",
    "activated_tm": "激活时间", "activatedtm": "激活时间",
    "check_tm": "检查时间", "checktm": "检查时间",
    "first_met_date": "初次见面日期", "firstmetdate": "初次见面日期",
    "cur_sleeping_event": "当前睡眠事件",
    "cursleepingevent": "当前睡眠事件", "curpersons": "当前角色",
    "destination": "目的地", "fromtime": "开始时间",
    "totime": "结束时间", "times": "次数",
    "scene_ref": "场景引用", "quest_chain": "任务链",
    "clothes": "服装", "outfit": "服装", "style": "风格",
    "fitness": "体质", "grade": "成绩", "grades": "成绩",
    "job": "工作", "work": "工作", "school": "学校",
    "money": "金钱", "cash": "现金", "debt": "债务",
    "rent": "房租", "salary": "工资", "income": "收入",
    "expense": "支出", "expenses": "支出", "bill": "账单",
    "bills": "账单", "loan": "贷款",

    # ---- 跨品类通用名词（RPG / 经营 / 科幻 / 校园 / 恐怖 / 奇幻）----
    "auto": "自动", "locked": "已锁定", "closed": "已关闭",
    "oxygen": "氧气", "battery": "电量", "flashlight": "手电筒",
    "phone": "电话", "dungeon": "地牢", "floor": "楼层",
    "route": "路线", "spell": "法术", "curse": "诅咒",
    "balance": "余额", "membership": "会员", "nightmare": "噩梦",
    "weekly": "每周", "open": "开放", "homework": "作业",
    "exam": "考试", "semester": "学期", "term": "学期",
    "class": "班级", "classroom": "教室", "teacher": "老师",
    "student": "学生", "principal": "校长", "employee": "员工",
    "morale": "士气", "ship": "飞船", "sector": "星区",
    "galaxy": "星系", "warp": "跃迁", "hull": "船体",
    "reactor": "反应堆", "drone": "无人机", "robot": "机器人",
    "cyborg": "改造人", "implant": "植入体", "chip": "芯片",
    "hack": "入侵", "hacked": "已入侵", "terminal": "终端",
    "scroll": "卷轴", "rune": "符文", "enchant": "附魔",
    "altar": "祭坛", "temple": "神庙", "priest": "祭司",
    "knight": "骑士", "sword": "剑", "bow": "弓", "arrow": "箭",
    "monster": "怪物", "demon": "恶魔", "angel": "天使",
    "dragon": "巨龙", "undead": "亡灵", "zombie": "丧尸",
    "ghost": "幽灵", "spirit": "灵魂", "meter": "计量表",
    "virus": "病毒", "medicine": "药品", "wound": "伤口",

    # ---- 亲属 / 家庭（本作大量以 T 结尾的关系称呼文本）----
    "aunt": "阿姨", "aunts": "阿姨", "auntie": "阿姨", "aunty": "阿姨",
    "uncle": "叔叔", "uncles": "叔叔",
    "bro": "兄弟", "brother": "兄弟", "brothers": "兄弟",
    "sis": "姐妹", "sister": "姐妹", "sisters": "姐妹",
    "dad": "爸爸", "father": "父亲", "myfather": "我父亲",
    "mom": "妈妈", "mommy": "妈妈", "momma": "妈妈", "mama": "妈妈",
    "mother": "母亲", "mymother": "我母亲", "mymom": "我妈妈",
    "son": "儿子", "sons": "儿子", "sonny": "儿子",
    "daughter": "女儿", "daughters": "女儿",
    "kid": "孩子", "kids": "孩子",
    "grandad": "爷爷", "granddad": "爷爷", "grandpa": "爷爷",
    "grandfather": "爷爷", "grandma": "奶奶", "grandmas": "奶奶",
    "grandmother": "奶奶", "grandmothers": "奶奶", "granny": "奶奶",
    "gran": "奶奶", "grans": "奶奶", "nana": "奶奶",
    "grandson": "孙子", "granddaughter": "孙女",
    "granddaughters": "孙女", "grandchildren": "孙辈",
    "nephew": "侄子", "nephews": "侄子", "niece": "侄女",
    "nieces": "侄女", "cousin": "表亲", "cousins": "表亲",
    "sibling": "兄弟姐妹", "siblings": "兄弟姐妹",
    "relative": "亲戚", "relatives": "亲戚", "families": "家庭",
    "parental": "父母", "parent": "父母", "parents": "父母",
    "myparents": "我父母", "half": "同父异母", "step": "继",
    "inlaw": "姻亲", "incest": "乱伦", "incestuous": "乱伦",
    "blood": "血缘", "bloodrelated": "血缘关系", "related": "亲属",
    "ownblood": "亲生", "myownblood": "亲生", "givenyoubirth": "生你",
    "twin": "双胞胎", "neighbor": "邻居", "neighbors": "邻居",
    "neighfamilyname": "邻居姓氏", "surname": "姓氏",
    "lover": "恋人", "girlfriend": "女友", "boyfriend": "男友",
    "wife": "妻子", "husband": "丈夫", "spouse": "配偶",

    # ---- 本作常见命名（GameData / 界面文本变量）----
    "gdata": "游戏数据", "ginitver": "初始版本", "gver": "版本",
    "adult": "成年", "adulttv": "成人电视", "tv18p": "18+电视",
    "pornotv": "成人电视", "booze": "酒", "inventory": "背包",
    "motel": "汽车旅馆", "house": "房屋", "firm": "事务所",
    "lawyer": "律师", "case": "案件", "visual": "视觉",
    "layout": "布局", "theme": "主题", "variant": "变体",
    "overlay": "覆盖层", "suppress": "隐藏", "started": "已开始",
    "visible": "可见", "mouse": "鼠标", "player": "玩家",
    "players": "玩家", "person": "人物", "persons": "人物",
    "big": "大", "threshold": "阈值", "modifier": "修正",
    "incr": "增量", "decr": "减量", "doze": "打盹", "say": "对话",
    "bad": "坏", "good": "好", "pct": "百分比", "percent": "百分比",
    "ratio": "比率", "factor": "系数", "mult": "倍率", "milt": "倍率",
    "given": "给予", "you": "你", "birth": "出生", "neigh": "邻居",
    "narrator": "旁白", "func": "函数", "itmp": "临时整数",
    "grand": "祖辈", "kin": "亲属", "motherly": "慈母",
    "sisterly": "姐妹般", "pdebug": "调试", "ptest": "测试",
    "basestring": "基础字符串", "extend": "扩展", "nvl": "NVL角色",
    "py": "Python版本", "notify": "通知", "rem": "剩余",
    "save": "存档", "shouse": "自家房屋", "var": "变量",
    "daily": "每日", "sub": "对象", "getyoubirth": "生你",

    # ---- 通用游戏机制（适配各类 Ren'Py / SLG，不限本作）----
    "date": "日期", "dating": "约会", "morning": "早晨", "noon": "中午",
    "evening": "傍晚", "night": "夜晚", "midnight": "午夜",
    "monday": "周一", "tuesday": "周二", "wednesday": "周三",
    "thursday": "周四", "friday": "周五", "saturday": "周六",
    "sunday": "周日", "weather": "天气", "rain": "雨天", "sunny": "晴天",
    "temperature": "温度", "home": "家", "office": "办公室",
    "shop": "商店", "market": "市场", "cafe": "咖啡馆", "gym": "健身房",
    "hospital": "医院", "park": "公园", "beach": "海滩", "club": "俱乐部",
    "hotel": "旅馆", "street": "街道", "city": "城市", "town": "城镇",
    "village": "村庄", "objective": "目标", "mission": "任务",
    "missions": "任务", "reward": "奖励", "rewards": "奖励",
    "penalty": "惩罚", "load": "读取", "autosave": "自动存档",
    "quicksave": "快速存档", "gallery": "画廊", "cg": "CG",
    "music": "音乐", "sound": "音效", "voice": "语音", "bgm": "背景音乐",
    "sfx": "音效", "volume": "音量", "mute": "静音", "skip": "跳过",
    "settings": "设置", "preferences": "偏好", "config": "配置",
    "language": "语言", "font": "字体", "achievement": "成就",
    "achievements": "成就", "trophy": "奖杯", "trophies": "奖杯",
    "collectible": "收集品", "collectibles": "收集品", "weapon": "武器",
    "armor": "护甲", "shield": "护盾", "damage": "伤害",
    "reload": "装填", "accuracy": "命中", "critical": "暴击",
    "dodge": "闪避", "block": "格挡", "heal": "治疗", "buff": "增益",
    "debuff": "减益", "cooldown": "冷却", "duration": "持续时间",
    "turn": "回合", "turns": "回合", "round": "轮次", "wave": "波次",
    "boss": "首领", "enemy": "敌人", "enemies": "敌人", "ally": "盟友",
    "allies": "盟友", "party": "派对", "member": "成员",
    "members": "成员", "guild": "公会", "clan": "氏族", "faction": "阵营",
    "tax": "税", "profit": "利润", "revenue": "收入", "wage": "工资",
    "discount": "折扣", "stock": "库存", "trade": "交易",
    "gift": "礼物", "gifts": "礼物", "present": "礼物",
    "flower": "花", "flowers": "花", "chocolate": "巧克力",
    "ring": "戒指", "necklace": "项链", "perfume": "香水",
    "bribe": "贿赂", "toy": "玩具", "toys": "玩具",
    "underwear": "内衣", "bra": "胸罩", "panties": "内裤",
    "dress": "连衣裙", "skirt": "裙子", "shoes": "鞋子",
    "costume": "服装", "uniform": "制服", "makeup": "妆容",
    "hair": "发型", "tattoo": "纹身", "piercing": "穿孔",
    "jewelry": "珠宝", "accessory": "饰品", "wardrobe": "衣柜",
    "outfit": "套装", "outfits": "套装", "clothes": "衣服",
    "pregnant": "怀孕", "contraception": "避孕", "condom": "避孕套",
    "fertility": "生育力", "libido": "性欲", "lactation": "泌乳",
    "gossip": "流言", "rumor": "谣言", "loyalty": "忠诚",
    "morale": "士气", "patience": "耐心", "tolerance": "容忍",
    "emotion": "情绪", "empathy": "共情", "leadership": "领导力",
    "timeofday": "时刻", "risk": "风险", "kiss": "亲吻",
    "kissed": "亲吻", "kissing": "亲吻", "cheat": "作弊",
    "cheats": "作弊", "mode": "模式", "last": "最近", "saved": "已保存",
    "girl": "女孩", "girls": "女孩", "boy": "男孩", "boys": "男孩",
    "npc": "NPC", "npcs": "NPC", "status": "状态",

    # ---- 葡萄牙语 ----
    "dinheiro": "金钱", "moeda": "硬币", "moedas": "硬币",
    "forca": "力量", "agilidade": "敏捷", "relacionamento": "关系",
    "namorada": "女友", "namorado": "男友", "esposa": "妻子",
    "marido": "丈夫", "filho": "儿子", "filha": "女儿",
    "mae": "妈妈", "pai": "爸爸", "irma": "姐妹", "irmao": "兄弟",
    "amiga": "朋友", "amigo": "朋友", "amante": "情人",

    # ---- 法语 ----
    "argent": "金钱", "monnaie": "零钱", "vie": "生命",
    "niveau": "等级", "force": "力量", "agilite": "敏捷",
    "charisme": "魅力", "chance": "幸运", "sagesse": "智慧",
    "attaque": "攻击", "vitesse": "速度", "magie": "魔力",
    "puissance": "战力", "mere": "妈妈", "pere": "爸爸",
    "frere": "兄弟", "soeur": "姐妹", "fille": "女儿",
    "fils": "儿子", "femme": "妻子", "mari": "丈夫",
    "ami": "朋友", "amie": "朋友", "amour": "爱意",
    "relation": "关系", "grossesse": "怀孕", "enceinte": "怀孕",
    "desir": "欲望", "plaisir": "快感", "obeissance": "服从",
    "soumission": "顺从", "confiance": "信任", "bonheur": "幸福",
    "tristesse": "悲伤", "colere": "愤怒", "peur": "恐惧",
    "honte": "羞耻", "volonte": "意志", "beaute": "美貌",
    "sante": "生命", "faim": "饥饿", "soif": "口渴",
}

# 修饰词：max_hp → 生命上限，total_money → 累计金钱
CN_SUFFIX_WORDS = {"max": "上限", "min": "下限", "bonus": "加成",
                   "extra": "额外", "additional": "额外", "value": "值"}
CN_PREFIX_WORDS = {
    "cur": "当前", "current": "当前", "now": "当前", "old": "旧",
    "prev": "之前", "base": "基础", "temp": "临时", "temporary": "临时",
    "total": "累计", "avg": "平均", "average": "平均", "show": "显示",
}

# 组合词里的连接词 / 类型标记，翻译时直接忽略：
# FamilyConflictToOpinionMax → 家庭冲突看法上限，AuntT → 阿姨
CN_DROP_WORDS = {"in", "of", "to", "into", "for", "with", "and", "the",
                 "a", "an", "my", "your", "our", "their", "his", "her",
                 "is", "as", "by", "on", "at", "from"}
# 单个字母结尾通常只是类型标记（T=文本 / F=数值 / S=集合），不参与翻译
CN_DROP_TAIL_LETTERS = {"t", "f", "s", "b", "n", "v", "d", "i", "l", "r"}

# 这类词太泛，单独翻出来反而会掩盖真实变量名（some_unknown_field 不该显示成「字段」）
CN_GENERIC_LABELS = {"字段", "对象", "数据", "值", "名称", "文本", "类型",
                     "标签", "列表", "表", "键", "序号", "集合", "条目"}

# 变量名里直接就是中文时，按这些词兜底识别
ATTR_CN_WORDS = ("金币", "金钱", "钻石", "水晶", "体力", "等级", "经验",
                 "魅力", "力量", "智力", "敏捷", "幸运", "声望", "技能",
                 "好感", "爱意", "堕落", "服从", "欲望", "信任")

CN_CAMEL_RE = re.compile(r"([a-z0-9])([A-Z])")
CN_SPLIT_RE = re.compile(r"[^0-9A-Za-z]+")
CN_TAIL_DIGITS_RE = re.compile(r"^(.*?)(\d+)$")


def _cn_tokens(name):
    """player_coins / playerCoins / g_amelia_heart[3] 统一拆成小写词"""
    text = CN_CAMEL_RE.sub(r"\1_\2", str(name or "")).lower()
    return [token for token in CN_SPLIT_RE.split(text) if token]


def _cn_lookup(token):
    """查词表，顺带处理复数与常见拼写变化"""
    if not token:
        return None
    label = ATTR_CN_LABELS.get(token)
    if label:
        return label
    for suffix in ("es", "s"):
        if token.endswith(suffix) and len(token) > len(suffix) + 2:
            label = ATTR_CN_LABELS.get(token[:-len(suffix)])
            if label:
                return label
    return None


def _cn_segment(token):
    """把连写的长词按词表切成已知词：charismashow → charisma + show

    只做「每个片段都在词表里」的切分，切不干净就放弃（返回 None）。
    """
    if len(token) < 5:
        return None
    pieces = []
    rest = token
    while rest:
        found = None
        for end in range(len(rest), 1, -1):
            candidate = rest[:end]
            if (candidate in ATTR_CN_LABELS or candidate in CN_SUFFIX_WORDS
                    or candidate in CN_PREFIX_WORDS):
                found = candidate
                break
        if not found:
            return None
        pieces.append(found)
        rest = rest[len(found):]
    return pieces if len(pieces) > 1 else None


def _cn_expand(tokens):
    """把连写片段展开成可翻译的词序列，展开不了的原样保留"""
    out = []
    for token in tokens:
        if (token in ATTR_CN_LABELS or token in CN_SUFFIX_WORDS
                or token in CN_PREFIX_WORDS or token in CN_DROP_WORDS
                or _cn_lookup(token) or len(token) < 5):
            out.append(token)
            continue
        pieces = _cn_segment(token)
        out.extend(pieces if pieces else [token])
    return out


def _has_cjk(text):
    """是否含有中文（用于判断搜索词要走中文兜底匹配）"""
    return any("\u4e00" <= char <= "\u9fff" for char in str(text or ""))


# 中文标签 → 英文变量名候选（供「按名称搜索」输入中文时反查）
CN_LABEL_INDEX = {}
for _cn_token, _cn_text in ATTR_CN_LABELS.items():
    CN_LABEL_INDEX.setdefault(_cn_text, []).append(_cn_token)


def _cn_keywords(text):
    """中文关键词 → 英文变量名候选；没有中文或查不到时返回空列表"""
    text = str(text or "").strip()
    if not _has_cjk(text):
        return []
    found = []
    for label, tokens in CN_LABEL_INDEX.items():
        if text in label or label in text:
            found.extend(tokens)
    found.sort(key=len, reverse=True)
    return list(dict.fromkeys(found))


def cn_label(name):
    """把变量名 / 字段名翻成中文；翻不出来返回 None（调用方保留原名）

    支持：g_amelia_heart → 好感，max_hp → 生命上限，total_money → 累计金钱，
    room_wt2 → 房间权重 2，rate3 → 评级 3，noraLove → 爱意
    """
    text = str(name or "")
    if not text:
        return None
    if any("\u4e00" <= char <= "\u9fff" for char in text):
        return text  # 已经是中文
    tokens = _cn_tokens(text)
    if not tokens:
        return None
    # 末尾数字当编号（列表下标 / 分阶段字段），字母数字混写也能拆：wt2 → wt + 2
    tail = ""
    if tokens and tokens[-1].isdigit():
        tail = tokens.pop()
    elif tokens:
        matched = CN_TAIL_DIGITS_RE.match(tokens[-1])
        if matched and matched.group(2):
            tokens[-1] = matched.group(1)
            tail = matched.group(2)
    if not tokens:
        return None
    # 结尾的单个字母通常只是类型标记（AuntT 的 T=文本），先去掉再整体查表：
    # InLawT → in_law → 姻亲，PornoTvT → porno_tv → 成人电视
    if len(tokens) > 1 and len(tokens[-1]) == 1 and tokens[-1] in CN_DROP_TAIL_LETTERS:
        tokens.pop()

    # 整体当组合词查（room_wt → 房间权重、display_order → 排序）
    joined = "_".join(tokens)
    label = ATTR_CN_LABELS.get(joined) or ATTR_CN_LABELS.get(joined.replace("_", ""))
    if label:
        return label + (" " + tail if tail else "")

    # 连写的长字段再按词表切一次：charismaShow / conflictsaythreshold
    tokens = _cn_expand(tokens)

    noun = None
    prefixes = []
    suffixes = []
    cores = []
    unknown = 0
    for token in tokens:
        if token in CN_SUFFIX_WORDS:
            suffixes.append(CN_SUFFIX_WORDS[token])
            continue
        if token in CN_PREFIX_WORDS:
            prefixes.append(CN_PREFIX_WORDS[token])
            continue
        if token in CN_DROP_WORDS:
            continue
        label = _cn_lookup(token)
        if label:
            if noun is None:
                noun = label
            cores.append(label)
        else:
            unknown += 1
    if noun is None:
        # 纯修饰词字段（Max / Min / Cur / Value）也能翻：上限 / 下限 / 当前 / 值
        if prefixes or suffixes:
            return "".join(dict.fromkeys(prefixes)) + "".join(
                dict.fromkeys(suffixes)) + (" " + tail if tail else "")
        return None
    # 只翻出一个泛化词时宁可保留原名，避免把 some_unknown_field 显示成「字段」
    if unknown and len(cores) == 1 and noun in CN_GENERIC_LABELS:
        return None
    # 多个可译词按顺序拼接：ShowAllure → 显示魅力、MaxHp → 生命上限
    # 即使有词翻不出来也保留已翻译的部分（autoSaveSlot → 自动存档槽位），
    # 只翻出一个词时只取名词，避免把修饰词堆成奇怪的名字。
    if len(cores) > 1:
        text_out = "".join(dict.fromkeys(prefixes)) + "".join(cores) + "".join(
            dict.fromkeys(suffixes))
    else:
        text_out = "".join(dict.fromkeys(prefixes)) + noun + "".join(
            dict.fromkeys(suffixes))
    return text_out + (" " + tail if tail else "")


def cn_path_label(path):
    """把完整变量路径逐段翻成中文：Relations.data.3.opinion.Value → 关系.数据.3.看法.值

    没有翻译出任何一段时返回 None（调用方保留原路径）。
    """
    text = str(path or "")
    if not text:
        return None
    parts = []
    changed = False
    for segment in text.split("."):
        if not segment or segment.isdigit():
            parts.append(segment)
            continue
        # 路径首段的 store / persistent 也翻成中文，避免中文名里混着英文前缀
        scope = CN_SCOPE_LABELS.get(segment.lower())
        if scope:
            changed = True
            parts.append(scope)
            continue
        label = cn_label(segment)
        if label:
            changed = True
            parts.append(label)
        else:
            parts.append(segment)
    return ".".join(parts) if changed else None


# 变量所在位置的中文叫法
CN_SCOPE_LABELS = {"store": "存档变量", "persistent": "持久变量",
                   "gui": "界面", "config": "配置"}


def cn_scope(value):
    """store / persistent → 存档变量 / 持久变量"""
    text = str(value or "")
    return CN_SCOPE_LABELS.get(text.lower(), text)


def cn_cell(name, raw=""):
    """列表里的「中文名」列：翻不出来就留空，原始名放进悬停提示"""
    text = str(name or "")
    label = cn_label(text)
    if not label and "." in text:
        # 属性名可能带归属前缀（Interests.Sports / dana.real_age），逐段翻译
        label = cn_path_label(text)
    item = QTableWidgetItem(label or "")
    item.setToolTip(raw or text)
    return item


def cn_path_cell(path):
    """按完整路径逐段翻译的「中文名」列"""
    text = str(path or "")
    item = QTableWidgetItem(cn_path_label(text) or "")
    item.setToolTip(text)
    return item


def query_path(page, path=""):
    """单个查询：读一个变量路径的当前值并弹窗展示，可一键复制路径 / 数值"""
    ctrl = page.ctrl
    if not ctrl.connected:
        ctrl.toast("请先连接游戏")
        return
    if not path:
        text, ok = QInputDialog.getText(
            page, "单个查询",
            "输入变量路径（可先右键「复制变量路径」再粘贴）：", text="")
        if not ok or not str(text).strip():
            return
        path = str(text).strip()
    ctrl.call("get", {"path": path},
              lambda data: _show_query_result(page, path, data),
              lambda message: QMessageBox.warning(page, "查询失败", message))


def _show_query_result(page, path, data):
    label = cn_path_label(path) or cn_label(str(path).split(".")[-1]) or ""
    lines = []
    if label:
        lines.append("中文名：%s" % label)
    lines.append("变量路径：%s" % path)
    lines.append("类型：%s" % (data.get("type") or ""))
    value = data.get("value")
    lines.append("当前值：%s" % ("" if value is None else value))
    box = QMessageBox(page)
    box.setWindowTitle("单个查询")
    box.setIcon(QMessageBox.Icon.Information)
    box.setText("\n".join(lines))
    path_btn = box.addButton("复制路径", QMessageBox.ButtonRole.ActionRole)
    value_btn = box.addButton("复制数值", QMessageBox.ButtonRole.ActionRole)
    box.addButton("关闭", QMessageBox.ButtonRole.AcceptRole)
    box.exec()
    clicked = box.clickedButton()
    if clicked == path_btn:
        page.ctrl.copy_text(path)
    elif clicked == value_btn:
        page.ctrl.copy_text("" if value is None else str(value))


def edit_path_value(page, path, on_after=None):
    """读取某个路径的当前值，弹输入框改好后写回（供收藏页 / 右键菜单复用）"""
    ctrl = page.ctrl
    if not ctrl.connected:
        ctrl.toast("请先连接游戏")
        return
    ctrl.call("get", {"path": path},
              lambda data: _show_value_editor(page, path, data, on_after),
              lambda message: QMessageBox.warning(page, "读取失败", message))


def _show_value_editor(page, path, data, on_after=None):
    before = str(data.get("value", ""))
    type_name = data.get("type", "")
    label = cn_path_label(path) or cn_label(str(path).split(".")[-1]) or path
    text, ok = QInputDialog.getText(
        page, "修改数值",
        "%s\n变量路径：%s\n类型：%s\n修改前：%s\n新值：" % (label, path, type_name, before),
        text=before,
    )
    if not ok:
        return
    page.ctrl.call("set", {"path": path, "value": text},
                   lambda result: _after_value_set(page, path, result, before, type_name, on_after),
                   lambda message: QMessageBox.warning(page, "修改失败", message))


def _after_value_set(page, path, result, before, type_name, on_after=None):
    after = result.get("value")
    page.ctrl.record_change(path, before, after, type_name)
    page.ctrl.log("已修改 %s：%s → %s" % (path, before, after))
    page.ctrl.toast("已修改 %s" % path)
    if on_after is not None:
        on_after(path, after)


def _cn_attr_label(entry):
    """把变量路径映射成中文名称；识别不出返回 None（不展示原始代码）"""
    label = cn_label(entry.get("name"))
    if label:
        return label
    text = "%s %s" % (entry.get("path") or "", entry.get("name") or "")
    for word in ATTR_CN_WORDS:
        if word in text:
            return word
    return cn_label(entry.get("path"))


# 这些字段是存档机制内部用的，改了对游戏基本没影响，默认折叠掉
CHAR_FIELD_INTERNAL = {"display_order", "test", "change"}


def _char_field_label(name):
    """角色字段转中文，识别不出保留原名"""
    return cn_label(name) or str(name or "")


def _note_cell(index):
    """双击是否落在最左侧「备注」列：是则交给表格自己进入备注编辑"""
    return index.column() == 0


def _path_of(table, row):
    """读取某行绑定的变量路径（路径存在单元格的 UserRole 里）"""
    for col in range(table.columnCount()):
        item = table.item(row, col)
        if item is None:
            continue
        data = item.data(Qt.ItemDataRole.UserRole)
        if data:
            return data
    item = table.item(row, 0)
    return item.text() if item is not None else ""


def _row_of_path(table, path):
    for row in range(table.rowCount()):
        if _path_of(table, row) == path:
            return row
    return -1


class PathEditDialog(QDialog):
    """手动按路径修改/新建变量"""

    TYPE_ITEMS = [
        ("自动（按原类型）", "auto"),
        ("整数", "int"),
        ("浮点数", "float"),
        ("文本", "str"),
        ("布尔", "bool"),
        ("列表", "list"),
        ("字典", "dict"),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("修改任意路径")
        self.setMinimumWidth(420)

        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.path_edit = QLineEdit()
        self.path_edit.setPlaceholderText("例如 money / player.gold / inventory.items.0")
        self.value_edit = QLineEdit()
        self.value_edit.setPlaceholderText("新值，列表/字典请填 Python 字面量，如 [1, 2] 或 {'a': 1}")
        self.type_box = QComboBox()
        for label, value in self.TYPE_ITEMS:
            self.type_box.addItem(label, value)
        self.create_box = QCheckBox("变量不存在时新建（仅支持 store 顶层名称）")
        form.addRow("路径", self.path_edit)
        form.addRow("新值", self.value_edit)
        form.addRow("类型", self.type_box)
        layout.addLayout(form)
        layout.addWidget(self.create_box)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def payload(self):
        return {
            "path": self.path_edit.text().strip(),
            "value": self.value_edit.text(),
            "value_type": self.type_box.currentData(),
            "create": self.create_box.isChecked(),
        }


class BasePage(QWidget):
    def __init__(self, ctrl):
        super().__init__()
        self.ctrl = ctrl
        self._find_box = None
        self._find_table = None
        self._find_escape = None

    def bind_find(self, box, table=None, enter_jump=True):
        """登记本页的搜索框与结果表格，供 Ctrl+F / Enter / F3 / Esc 使用"""
        self._find_box = box
        self._find_table = table
        if box is None:
            return
        tip = box.toolTip()
        box.setToolTip((tip + "\n" if tip else "")
                       + "Ctrl+F 快速查找 · Enter 跳到第一条结果 · Esc 退出查找")
        if enter_jump:
            box.returnPressed.connect(self.focus_first_result)
        escape = QShortcut(QKeySequence("Esc"), box)
        escape.setContext(Qt.ShortcutContext.WidgetShortcut)
        escape.activated.connect(self._escape_find)
        self._find_escape = escape

    def search_box(self):
        """Ctrl+F 要聚焦的搜索框；本页没有搜索框时返回 None"""
        return self._find_box

    def result_table(self):
        """搜索结果表格，供 Enter / F3 跳转"""
        return self._find_table

    def focus_first_result(self):
        table = self._find_table
        if table is None or table.rowCount() == 0:
            return
        table.selectRow(0)
        table.setFocus()

    def _escape_find(self):
        """Esc：清空搜索框并回到结果表格"""
        box = self._find_box
        if box is None:
            return
        box.clear()
        box.clearFocus()
        if self._find_table is not None:
            self._find_table.setFocus()

    def poll_if_needed(self):
        pass

    def refresh(self):
        pass

    def on_connection_changed(self, connected):
        pass

    def toggle_favorite(self, path, name="", type_name=""):
        """收藏 / 取消收藏一个变量路径"""
        ctrl = self.ctrl
        if not path:
            ctrl.toast("没有可收藏的变量路径")
            return
        label = cn_path_label(path) or cn_label(name) or path
        if ctrl.is_favorite(path):
            if ctrl.favorite_remove(path):
                ctrl.toast("已取消收藏：" + label)
            return
        label = cn_label(name) or cn_path_label(path) or str(path).split(".")[-1]
        if ctrl.favorite_add(path, label, type_name):
            ctrl.toast("已收藏：%s（可在「收藏修改」页直接改）" % label)
        else:
            ctrl.toast("已在收藏中：" + label)

    def favorite_action(self, path, name="", type_name=""):
        """右键菜单里的「收藏此值 / 取消收藏」"""
        liked = bool(self.ctrl.is_favorite(path))
        action = QAction("取消收藏" if liked else "收藏此值", self)
        action.triggered.connect(
            lambda: self.toggle_favorite(path, name, type_name))
        return action


class FavoritesPage(BasePage):
    """收藏修改：把常用数值（金币、好感等）收藏起来，下次直接在这里改"""

    def __init__(self, ctrl):
        super().__init__(ctrl)
        self._busy = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)
        self.filter_edit = QLineEdit()
        self.filter_edit.setPlaceholderText("按名称 / 中文名 / 路径过滤…")
        self.filter_edit.setFixedWidth(240)
        self.filter_edit.textChanged.connect(lambda _: self.reload())
        tip = QLabel("在其他页面右键「收藏此值」即可加到这里")
        tip.setObjectName("muted")
        self.refresh_btn = QPushButton("刷新当前值")
        self.refresh_btn.clicked.connect(self.refresh_values)
        self.edit_btn = QPushButton("修改值…")
        self.edit_btn.clicked.connect(self._edit_selected)
        self.remove_btn = QPushButton("取消收藏")
        self.remove_btn.clicked.connect(self._remove_selected)
        self.record_btn = QPushButton("加入记录")
        self.record_btn.clicked.connect(self._record_selected)
        toolbar.addWidget(self.filter_edit)
        toolbar.addWidget(tip, 1)
        toolbar.addWidget(self.refresh_btn)
        toolbar.addWidget(self.edit_btn)
        toolbar.addWidget(self.remove_btn)
        toolbar.addWidget(self.record_btn)
        layout.addLayout(toolbar)

        self.table = make_table(["名称", "中文名", "类型", "当前值", "变量路径"], ctrl=self.ctrl)
        self.table.setColumnWidth(0, 180)
        self.table.setColumnWidth(1, 120)
        self.table.setColumnWidth(2, 70)
        self.table.setColumnWidth(3, 110)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.doubleClicked.connect(self._on_double_click)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._on_context_menu)
        layout.addWidget(self.table, 1)

        self.status = QLabel("双击某行可直接改值；Ctrl / Shift 多选后可批量改值、批量取消收藏。")
        self.status.setObjectName("muted")
        layout.addWidget(self.status)
        self.bind_find(self.filter_edit, self.table)

        self.reload()

    # ---- 数据 ----
    def reload(self):
        keyword = self.filter_edit.text().strip().lower()
        items = list(self.ctrl.favorites.items)
        if keyword:
            items = [item for item in items
                     if keyword in str(item.get("path") or "").lower()
                     or keyword in str(item.get("name") or "").lower()
                     or keyword in str(item.get("cn") or "").lower()]
        table = self.table
        table.setUpdatesEnabled(False)
        table.setRowCount(len(items))
        for row, item in enumerate(items):
            path = str(item.get("path") or "")
            name = str(item.get("name") or path)
            name_item = QTableWidgetItem(name)
            name_item.setData(Qt.ItemDataRole.UserRole, path)
            name_item.setToolTip(path)
            table.setItem(row, 0, name_item)
            table.setItem(row, 1, QTableWidgetItem(str(item.get("cn") or cn_path_label(path) or "")))
            table.setItem(row, 2, QTableWidgetItem(str(item.get("type") or "")))
            table.setItem(row, 3, QTableWidgetItem(str(item.get("value") or "")))
            table.setItem(row, 4, QTableWidgetItem(path))
        table.setUpdatesEnabled(True)
        if self.ctrl.connected:
            self.refresh_values()

    def refresh_values(self):
        if not self.ctrl.connected:
            self.ctrl.toast("请先连接游戏")
            return
        if self._busy or self.table.rowCount() == 0:
            return
        self._busy = True
        paths = [_path_of(self.table, row) for row in range(self.table.rowCount())]
        pending = {"count": len([path for path in paths if path])}
        if pending["count"] == 0:
            self._busy = False
            return
        for path in paths:
            if not path:
                continue
            self.ctrl.call("get", {"path": path},
                           lambda data, item_path=path: self._on_value(item_path, data, pending),
                           lambda message, item_path=path: self._on_value_error(item_path, message, pending))

    def _on_value(self, path, data, pending):
        row = _row_of_path(self.table, path)
        if row >= 0:
            value_item = QTableWidgetItem("" if data.get("value") is None else str(data.get("value")))
            value_item.setToolTip(path)
            self.table.setItem(row, 3, value_item)
            type_item = self.table.item(row, 2)
            if type_item is not None and data.get("type"):
                type_item.setText(str(data.get("type")))
            self.ctrl.favorites.set_value(path, data.get("value"), data.get("type") or "")
        pending["count"] -= 1
        if pending["count"] <= 0:
            self._busy = False

    def _on_value_error(self, path, message, pending):
        pending["count"] -= 1
        if pending["count"] <= 0:
            self._busy = False

    def _selected_paths(self):
        rows = sorted({index.row() for index in self.table.selectedIndexes()})
        return [_path_of(self.table, row) for row in rows if _path_of(self.table, row)]

    def _on_double_click(self, index):
        if _note_cell(index):
            return
        path = _path_of(self.table, index.row())
        if path:
            self._edit_path(path)

    def _edit_path(self, path):
        edit_path_value(self, path, self._after_edit)

    def _after_edit(self, path, after):
        row = _row_of_path(self.table, path)
        if row >= 0:
            item = QTableWidgetItem("" if after is None else str(after))
            item.setForeground(Qt.GlobalColor.green)
            item.setToolTip(path)
            self.table.setItem(row, 3, item)
        self.ctrl.favorites.set_value(path, after, "")

    def _edit_selected(self):
        paths = self._selected_paths()
        if not paths:
            self.ctrl.toast("请先选择要修改的收藏项")
            return
        if len(paths) == 1:
            self._edit_path(paths[0])
            return
        text, ok = QInputDialog.getText(
            self, "批量修改收藏", "把选中的 %d 项都设为：" % len(paths), text="")
        if not ok or not str(text).strip():
            return
        target = str(text).strip()
        before = {}
        for path in paths:
            row = _row_of_path(self.table, path)
            cell = self.table.item(row, 3) if row >= 0 else None
            before[path] = cell.text() if cell else ""
        for path in paths:
            self.ctrl.call(
                "set", {"path": path, "value": target},
                lambda result, item_path=path: self._on_batch_set(item_path, result, target, before),
                lambda message, item_path=path: self.ctrl.log(
                    "批量修改失败 %s：%s" % (item_path, message)),
            )

    def _on_batch_set(self, path, result, target, before):
        row = _row_of_path(self.table, path)
        after = result.get("value")
        if row >= 0:
            item = QTableWidgetItem("" if after is None else str(after))
            item.setForeground(Qt.GlobalColor.green)
            item.setToolTip(path)
            self.table.setItem(row, 3, item)
        type_item = self.table.item(row, 2) if row >= 0 else None
        type_name = type_item.text() if type_item else ""
        self.ctrl.record_change(path, before.get(path, ""), after, type_name)
        self.ctrl.favorites.set_value(path, after, type_name)
        self.ctrl.log("已修改 %s：%s → %s" % (path, before.get(path, ""), after))

    def _remove_selected(self):
        paths = self._selected_paths()
        if not paths:
            self.ctrl.toast("请先选择要取消收藏的项")
            return
        for path in paths:
            self.ctrl.favorites.remove(path)
        self.ctrl.toast("已取消收藏 %d 项" % len(paths))
        self.reload()

    def _record_selected(self):
        paths = self._selected_paths()
        if not paths:
            self.ctrl.toast("请先选择要加入记录的项")
            return
        added = 0
        for path in paths:
            if self.ctrl.has_record(path):
                continue
            row = _row_of_path(self.table, path)
            value_item = self.table.item(row, 3) if row >= 0 else None
            type_item = self.table.item(row, 2) if row >= 0 else None
            self.ctrl.record_change(
                path,
                value_item.text() if value_item else "",
                "—",
                type_item.text() if type_item else "",
            )
            added += 1
        self.ctrl.toast("已加入修改记录 %d 项" % added if added else "选中的都已记录")

    def _on_context_menu(self, pos):
        index = self.table.indexAt(pos)
        if not index.isValid():
            return
        row = index.row()
        if row not in {i.row() for i in self.table.selectedIndexes()}:
            self.table.selectRow(row)
        path = _path_of(self.table, row)
        if not path:
            return
        menu = QMenu(self)
        edit_action = QAction("修改值…", self)
        edit_action.triggered.connect(lambda: self._edit_path(path))
        query_action = QAction("单个查询…", self)
        query_action.triggered.connect(lambda: query_path(self, path))
        record_action = QAction("加入修改记录", self)
        record_action.triggered.connect(self._record_selected)
        remove_action = QAction("取消收藏", self)
        remove_action.triggered.connect(self._remove_selected)
        copy_path_action = QAction("复制变量路径", self)
        copy_path_action.triggered.connect(lambda: self.ctrl.copy_text(path))
        value_item = self.table.item(row, 3)
        copy_value_action = QAction("复制当前值", self)
        copy_value_action.triggered.connect(
            lambda: self.ctrl.copy_text(value_item.text() if value_item else ""))
        menu.addAction(edit_action)
        menu.addAction(record_action)
        menu.addAction(remove_action)
        menu.addSeparator()
        menu.addAction(query_action)
        menu.addAction(copy_path_action)
        menu.addAction(copy_value_action)
        menu.exec(self.table.viewport().mapToGlobal(pos))


class VariablesPage(BasePage):
    def __init__(self, ctrl):
        super().__init__(ctrl)
        self._busy = False
        self._filter_timer = QTimer(self)
        self._filter_timer.setSingleShot(True)
        self._filter_timer.setInterval(300)
        self._filter_timer.timeout.connect(self.refresh)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)
        self.filter_edit = QLineEdit()
        self.filter_edit.setPlaceholderText("按变量名过滤，可输入中文（如金钱 / 好感）…")
        self.filter_edit.setFixedWidth(230)
        self.filter_edit.textChanged.connect(lambda _: self._filter_timer.start())
        self.objects_box = QCheckBox("显示对象")
        self.objects_box.setChecked(bool(ctrl.settings.data.get("show_objects", False)))
        self.objects_box.stateChanged.connect(self._on_objects_changed)
        self.auto_box = QCheckBox("自动刷新")
        self.auto_box.setChecked(bool(ctrl.settings.data.get("auto_refresh", True)))
        self.auto_box.stateChanged.connect(self._on_auto_changed)
        refresh_btn = QPushButton("刷新")
        refresh_btn.clicked.connect(self.refresh)
        path_btn = QPushButton("修改任意路径…")
        path_btn.clicked.connect(self._open_path_editor)
        toolbar.addWidget(self.filter_edit)
        toolbar.addWidget(self.objects_box)
        toolbar.addWidget(self.auto_box)
        toolbar.addStretch(1)
        toolbar.addWidget(refresh_btn)
        toolbar.addWidget(path_btn)
        layout.addLayout(toolbar)

        self.table = make_table(["变量名", "中文名", "类型", "当前值"], ctrl=self.ctrl)
        self.table.setColumnWidth(0, 230)
        self.table.setColumnWidth(1, 130)
        self.table.setColumnWidth(2, 80)
        self.table.doubleClicked.connect(self._on_double_click)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._on_context_menu)
        layout.addWidget(self.table, 1)

        self.hint = QLabel("双击变量可改值，右键可锁定数值（锁定后游戏内会持续保持该值）。")
        self.hint.setObjectName("muted")
        layout.addWidget(self.hint)
        self.bind_find(self.filter_edit, self.table)

    # ---- 生命周期 ----
    def poll_if_needed(self):
        if self.auto_box.isChecked():
            self.refresh()

    def refresh(self):
        if not self.ctrl.connected or self._busy:
            return
        self._busy = True
        self.ctrl.call(
            "list",
            {
                "scope": "store",
                "filter": "" if _has_cjk(self.filter_edit.text()) else self.filter_edit.text().strip(),
                "objects": self.objects_box.isChecked(),
            },
            self._on_data,
            self._on_error,
        )

    def _on_data(self, data):
        self._busy = False
        if not self.isVisible():
            return
        items = data.get("items") or []
        keyword = self.filter_edit.text().strip()
        if _has_cjk(keyword):
            # 中文搜索：服务端只认英文名，这里按中文映射 / 原名 / 路径本地兜底
            keyword = keyword.lower()
            items = [item for item in items
                     if keyword in str(item.get("name") or "").lower()
                     or keyword in str(item.get("path") or "").lower()
                     or keyword in (cn_label(item.get("name")) or "")]
        table = self.table
        selected = ""
        row = table.currentRow()
        if row >= 0:
            selected = _path_of(table, row)

        table.setUpdatesEnabled(False)
        table.setRowCount(len(items))
        for index, item in enumerate(items):
            path = item.get("path") or item.get("name") or ""
            raw_name = item.get("name") or path
            name_item = QTableWidgetItem(raw_name)
            name_item.setData(Qt.ItemDataRole.UserRole, path)
            name_item.setToolTip("%s\n%s" % (raw_name, path))
            cn_item = cn_cell(raw_name, path)
            type_item = QTableWidgetItem(item.get("type") or "")
            value_item = QTableWidgetItem(item.get("value") or "")
            value_item.setToolTip(item.get("value") or "")
            if item.get("frozen"):
                name_item.setText("[锁定] " + raw_name)
                type_item.setText((item.get("type") or "") + " · 已锁定")
                for cell in (name_item, cn_item, type_item, value_item):
                    cell.setForeground(Qt.GlobalColor.yellow)
            table.setItem(index, 0, name_item)
            table.setItem(index, 1, cn_item)
            table.setItem(index, 2, type_item)
            table.setItem(index, 3, value_item)
        table.setUpdatesEnabled(True)

        row = _row_of_path(table, selected)
        if row >= 0:
            table.selectRow(row)

        if _has_cjk(self.filter_edit.text()):
            text = "共 %d 个变量（按中文名筛选）" % len(items)
        else:
            text = "共 %d 个变量" % data.get("count", len(items))
        if data.get("capped"):
            text += "（已截断显示前 3000 个）"
        self.hint.setText(text + " · 双击修改，右键锁定 · Ctrl+F 查找")

    def _on_error(self, _message):
        self._busy = False

    # ---- 交互 ----
    def _on_objects_changed(self):
        self.ctrl.settings.data["show_objects"] = self.objects_box.isChecked()
        self.ctrl.settings.save()
        self.refresh()

    def _on_auto_changed(self):
        self.ctrl.settings.data["auto_refresh"] = self.auto_box.isChecked()
        self.ctrl.settings.save()

    def _on_double_click(self, index):
        if _note_cell(index):
            return
        row = index.row()
        path = _path_of(self.table, row)
        if not path:
            return
        type_item = self.table.item(row, 2)
        type_name = (type_item.text() if type_item else "").split(" · ")[0]
        if type_name not in ELEMENTARY_TYPES and not self.objects_box.isChecked():
            QMessageBox.information(
                self, "提示",
                "该变量是列表 / 字典 / 对象，不能直接按文本修改。\n"
                "请使用右上角「修改任意路径…」编辑它的内部路径。",
            )
            return
        self._edit_path(path)

    def _edit_path(self, path):
        self.ctrl.call(
            "get",
            {"path": path},
            lambda data: self._show_edit_dialog(path, data),
            self._on_edit_error,
        )

    def _show_edit_dialog(self, path, data):
        if not data.get("editable"):
            QMessageBox.information(
                self, "提示",
                "该变量是列表 / 字典 / 对象，请使用「修改任意路径…」按具体属性修改。",
            )
            return
        before = str(data.get("value", ""))
        type_name = data.get("type", "")
        text, ok = QInputDialog.getText(
            self, "修改变量",
            "%s（%s）\n修改前：%s\n新值：" % (path, type_name, before),
            text=before,
        )
        if not ok:
            return
        self.ctrl.call(
            "set",
            {"path": path, "value": text},
            lambda result: self._after_set(path, result, before, type_name),
        )

    def _after_set(self, path, result, before=None, type_name=""):
        after = result.get("value")
        self.ctrl.log("已修改 %s：%s → %s" % (path, before, after))
        if before is not None:
            self.ctrl.record_change(path, before, after, type_name)
        self.refresh()

    def _on_edit_error(self, message):
        QMessageBox.warning(self, "修改失败", message)

    def _add_to_records(self, path):
        self.ctrl.call(
            "get",
            {"path": path},
            lambda data: self._confirm_add_record(path, data),
            lambda message: QMessageBox.warning(self, "读取失败", message),
        )

    def _confirm_add_record(self, path, data):
        if self.ctrl.has_record(path):
            note, ok = QInputDialog.getText(self, "修改备注", "%s 已在记录中，备注：" % path)
            if ok:
                self.ctrl.update_record(path, note=note.strip())
            return
        note, ok = QInputDialog.getText(self, "加入修改记录", "%s 的备注（可留空）：" % path)
        if not ok:
            return
        self.ctrl.record_change(path, data.get("value"), "—", data.get("type", ""), note=note.strip())
        self.ctrl.toast("已加入修改记录：" + path)

    def _on_context_menu(self, pos):
        index = self.table.indexAt(pos)
        if not index.isValid():
            return
        row = index.row()
        path = _path_of(self.table, row)
        if not path:
            return
        menu = QMenu(self)
        name_item = self.table.item(row, 0)
        type_item = self.table.item(row, 2)
        menu.addAction(self.favorite_action(
            path,
            name_item.text() if name_item else "",
            type_item.text() if type_item else "",
        ))
        menu.addSeparator()
        edit_action = QAction("修改值…", self)
        edit_action.triggered.connect(lambda: self._edit_path(path))
        record_action = QAction("加入修改记录…", self)
        record_action.triggered.connect(lambda: self._add_to_records(path))
        freeze_action = QAction("锁定此值", self)
        freeze_action.triggered.connect(lambda: self._freeze(path))
        copy_action = QAction("复制变量名", self)
        copy_action.triggered.connect(lambda: self.ctrl.copy_text(path))
        menu.addAction(edit_action)
        menu.addAction(record_action)
        menu.addAction(freeze_action)
        menu.addSeparator()
        menu.addAction(copy_action)
        menu.exec(self.table.viewport().mapToGlobal(pos))

    def _freeze(self, path):
        self.ctrl.call(
            "freeze",
            {"path": path},
            lambda data: self._after_freeze(path, data),
            lambda message: QMessageBox.warning(self, "锁定失败", message),
        )

    def _after_freeze(self, path, data):
        self.ctrl.log("已锁定 %s = %s" % (path, data.get("value")))
        if self.ctrl.has_record(path):
            self.ctrl.update_record(path, frozen=True)
        else:
            self.ctrl.record_change(path, data.get("value"), data.get("value"), frozen=True)
        self.ctrl.refresh_current()

    def _open_path_editor(self):
        if not self.ctrl.connected:
            QMessageBox.information(self, "未连接", "请先连接游戏后再操作。")
            return
        dialog = PathEditDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        payload = dialog.payload()
        if not payload["path"]:
            return
        self.ctrl.call(
            "set",
            payload,
            lambda result: self._after_set(payload["path"], result),
            lambda message: QMessageBox.warning(self, "修改失败", message),
        )


class SearchPage(BasePage):
    def __init__(self, ctrl):
        super().__init__(ctrl)
        self.scans = 0
        self._busy = False
        self._items_all = []
        self._history = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)
        label = QLabel("搜索数值")
        label.setObjectName("section")
        self.value_edit = QLineEdit()
        self.value_edit.setPlaceholderText("要搜索的数值，例如金币 1000")
        self.value_edit.setFixedWidth(240)
        self.value_edit.returnPressed.connect(lambda: self._scan("new"))
        self.first_btn = QPushButton("首次扫描")
        self.first_btn.setObjectName("primary")
        self.first_btn.clicked.connect(lambda: self._scan("new"))
        self.next_btn = QPushButton("再次扫描")
        self.next_btn.clicked.connect(lambda: self._scan("next"))
        self.reset_btn = QPushButton("重置")
        self.reset_btn.clicked.connect(self._reset)
        for btn in (self.first_btn, self.next_btn, self.reset_btn):
            btn.setEnabled(False)
        toolbar.addWidget(label)
        toolbar.addWidget(self.value_edit)
        toolbar.addWidget(self.first_btn)
        toolbar.addWidget(self.next_btn)
        toolbar.addWidget(self.reset_btn)
        toolbar.addStretch(1)
        layout.addLayout(toolbar)

        # 按属性名直接搜索：不用知道数值，输入 strength / massage / money 这类名字即可
        name_row = QHBoxLayout()
        name_row.setSpacing(8)
        name_label = QLabel("按名称搜索")
        name_label.setObjectName("section")
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("属性名，如 strength / money，也可输入中文（金钱 / 好感 / 魅力）")
        self.name_edit.setFixedWidth(240)
        self.name_edit.returnPressed.connect(self._find)
        self.find_btn = QPushButton("搜索属性名")
        self.find_btn.clicked.connect(self._find)
        self.find_btn.setEnabled(False)
        name_row.addWidget(name_label)
        name_row.addWidget(self.name_edit)
        name_row.addWidget(self.find_btn)
        name_row.addStretch(1)
        layout.addLayout(name_row)

        # 在当前结果里按名称 / 中文名 / 路径 / 值二次筛选：
        # 扫 1000 命中一百多条后，直接在这里输入 love / 金钱 就能缩小范围，
        # 不会像「按名称搜索」那样重新去全库搜、把结果整张表换掉。
        filter_row = QHBoxLayout()
        filter_row.setSpacing(8)
        filter_label = QLabel("结果内筛选")
        filter_label.setObjectName("section")
        self.filter_edit = QLineEdit()
        self.filter_edit.setPlaceholderText("在当前结果里筛选：名称 / 中文名 / 路径 / 当前值，如 love、金钱、dana")
        self.filter_edit.setFixedWidth(360)
        self.filter_edit.textChanged.connect(lambda _text: self._apply_filter())
        self.filter_hint = QLabel("")
        self.filter_hint.setObjectName("muted")
        filter_row.addWidget(filter_label)
        filter_row.addWidget(self.filter_edit)
        filter_row.addWidget(self.filter_hint)
        filter_row.addStretch(1)
        layout.addLayout(filter_row)

        self.table = make_table(["变量名", "中文名", "类型", "当前值", "修改前", "首次值"],
                                ctrl=self.ctrl)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.setColumnWidth(0, 230)
        self.table.setColumnWidth(1, 130)
        self.table.setColumnWidth(2, 70)
        self.table.setColumnWidth(3, 100)
        self.table.setColumnWidth(4, 100)
        self.table.setColumnWidth(5, 100)
        self.table.doubleClicked.connect(self._on_double_click)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._on_context_menu)
        layout.addWidget(self.table, 1)
        self.bind_find(self.name_edit, self.table, enter_jump=False)

        bottom = QHBoxLayout()
        self.status = QLabel("尚未扫描：先输入游戏中的数值点「首次扫描」，回游戏花掉/获得数值后再点「再次扫描」缩小范围。"
                             "　Ctrl / Shift 可多选，批量修改 / 锁定 / 加记录。")
        self.status.setObjectName("muted")
        self.edit_btn = QPushButton("修改选中")
        self.edit_btn.clicked.connect(self._edit_selected)
        self.freeze_btn = QPushButton("锁定选中")
        self.freeze_btn.clicked.connect(self._freeze_selected)
        self.record_btn = QPushButton("加入记录")
        self.record_btn.clicked.connect(self._add_selected_to_records)
        for btn in (self.edit_btn, self.freeze_btn, self.record_btn):
            btn.setEnabled(False)
        bottom.addWidget(self.status, 1)
        bottom.addWidget(self.record_btn)
        bottom.addWidget(self.edit_btn)
        bottom.addWidget(self.freeze_btn)
        layout.addLayout(bottom)

    def on_connection_changed(self, connected):
        for btn in (self.first_btn, self.next_btn, self.reset_btn, self.edit_btn,
                    self.freeze_btn, self.record_btn, self.find_btn):
            btn.setEnabled(connected)
        self.name_edit.setEnabled(connected)
        if connected:
            if self.scans == 0:
                self.status.setText(
                    "先输入游戏中的数值点「首次扫描」，回游戏花掉/获得数值后再点「再次扫描」缩小范围。"
                )
        else:
            self.status.setText("未连接游戏：请在左侧点「连接」，右上角显示「已连接」后再扫描。")

    def _scan(self, mode):
        if not self.ctrl.connected:
            self.ctrl.toast("请先连接游戏")
            return
        if mode == "next" and self.scans <= 0:
            self.ctrl.toast("请先执行一次「首次扫描」")
            return
        if self._busy:
            return
        text = self.value_edit.text().strip()
        if not text:
            self.ctrl.toast("请输入要搜索的数值")
            return
        self._busy = True
        if mode == "new" and self.filter_edit.text():
            # 新一轮扫描是全新的结果集，旧的筛选词先清掉，避免看着像「扫不到」
            self.filter_edit.blockSignals(True)
            self.filter_edit.clear()
            self.filter_edit.blockSignals(False)
        # 深度扫描要下钻到 opinion.Value 这类第 4 层，耗时比原来长，放宽超时
        self.ctrl.call(
            "scan",
            {"value": text, "mode": mode},
            lambda data: self._on_scan(data, mode),
            self._on_scan_error,
            timeout=15.0,
        )

    def _on_scan(self, data, mode):
        self._busy = False
        items = data.get("items") or []
        count = data.get("count", len(items))
        if mode == "new" or (mode == "next" and self.scans <= 0):
            self.scans = 1
        else:
            self.scans += 1
            if count == 0:
                self.scans = 1
        table = self.table
        # 继续筛选时保留「修改前 / 首次值」，像 CE 一样不会因为改过值就丢行
        history = {}
        if mode == "next":
            for row in range(table.rowCount()):
                old_path = _path_of(table, row)
                if not old_path:
                    continue
                before_cell = table.item(row, 4)
                first_cell = table.item(row, 5)
                history[old_path] = (
                    before_cell.text() if before_cell else "—",
                    first_cell.text() if first_cell else "",
                )
        self._render(items, history)

        text = "第 %d 次扫描：命中 %d 个变量" % (self.scans, count)
        if data.get("capped"):
            text += "（仅显示前 500 个）"
        if count == 0:
            if data.get("store_size") == 0:
                text += ("。游戏当前 store 为 0，还停在主菜单/标题界面，"
                         "请先「开始游戏」或「读取存档」，进游戏后再扫描")
            else:
                text += "，请换个数值重新「首次扫描」"
        self.status.setText(text)

    def _on_scan_error(self, message):
        self._busy = False
        self.ctrl.toast(message)

    def _render(self, items, history=None):
        """保存完整结果，再按「结果内筛选」框决定实际显示哪些行"""
        self._items_all = list(items or [])
        self._history = history or {}
        self._apply_filter()

    @staticmethod
    def _item_hit(item, keyword):
        """一条结果是否命中筛选词：变量名 / 中文名 / 完整路径 / 类型 / 当前值"""
        raw_name = str(item.get("name") or "")
        path = str(item.get("path") or "")
        candidates = [raw_name, path, item.get("type"), item.get("value"),
                      item.get("owner")]
        if "." in raw_name:
            candidates.append(cn_path_label(raw_name))
        else:
            candidates.append(cn_label(raw_name))
        candidates.append(cn_path_label(path))
        for text in candidates:
            if keyword in str(text or "").lower():
                return True
        return False

    def _apply_filter(self):
        """按「结果内筛选」框过滤当前结果，不重新向游戏请求数据"""
        keyword = self.filter_edit.text().strip().lower()
        items = self._items_all
        shown = items
        if keyword:
            shown = [item for item in items if self._item_hit(item, keyword)]
        self._render_rows(shown, self._history)
        if items:
            self.filter_hint.setText(
                ("显示 %d / %d 项" % (len(shown), len(items))) if keyword
                else ("共 %d 项" % len(items)))
        else:
            self.filter_hint.setText("")

    def _render_rows(self, items, history=None):
        """把结果写进表格；history 提供「修改前 / 首次值」的旧状态"""
        table = self.table
        history = history or {}
        table.setUpdatesEnabled(False)
        table.setRowCount(len(items))
        for index, item in enumerate(items):
            path = item.get("path") or item.get("name") or ""
            raw_name = item.get("name") or path
            name_item = QTableWidgetItem(raw_name)
            name_item.setData(Qt.ItemDataRole.UserRole, path)
            name_item.setToolTip("%s\n%s\n%s" % (raw_name, path, item.get("owner") or ""))
            table.setItem(index, 0, name_item)
            table.setItem(index, 1, cn_cell(raw_name, path))
            table.setItem(index, 2, QTableWidgetItem(item.get("type") or ""))
            value_text = item.get("value") or ""
            before_text, first_text = history.get(path, ("—", value_text))
            value_item = QTableWidgetItem(value_text)
            value_item.setToolTip(value_text)
            table.setItem(index, 3, value_item)
            edit_item = QTableWidgetItem(before_text)
            edit_item.setToolTip("修改前的值")
            table.setItem(index, 4, edit_item)
            first_item = QTableWidgetItem(first_text)
            first_item.setToolTip("第一次扫描时的值")
            table.setItem(index, 5, first_item)
        table.setUpdatesEnabled(True)

    def _find(self):
        """按属性名 / 变量名直接搜索，不需要先知道数值"""
        if not self.ctrl.connected:
            self.ctrl.toast("请先连接游戏")
            return
        keyword = self.name_edit.text().strip()
        if not keyword:
            self.ctrl.toast("请输入要搜索的属性名")
            return
        if self.filter_edit.text():
            # 按名称搜索是全库搜索，会整表替换结果，旧的筛选词先清掉
            self.filter_edit.blockSignals(True)
            self.filter_edit.clear()
            self.filter_edit.blockSignals(False)
        candidates = _cn_keywords(keyword)
        if candidates:
            # 输入了中文：工具界面显示中文名，但游戏里的变量是英文名，
            # 所以先反查出英文候选，再逐个搜索后合并结果。
            self._pending_find = candidates[:6]
            self._find_items = []
            self._find_keyword = keyword
            self._find_step()
            return
        self.find_btn.setEnabled(False)
        self.ctrl.call(
            "find",
            {"keyword": keyword, "limit": 300},
            lambda data: self._on_find(keyword, data),
            self._on_find_error,
        )

    def _find_step(self):
        """中文搜索：逐个英文候选请求，最后合并显示"""
        if not self._pending_find:
            self.find_btn.setEnabled(True)
            merged = {}
            for item in self._find_items:
                merged.setdefault(item.get("path") or item.get("name"), item)
            self._on_find(self._find_keyword, {"items": list(merged.values())})
            return
        token = self._pending_find.pop(0)
        self.find_btn.setEnabled(False)
        self.ctrl.call(
            "find",
            {"keyword": token, "limit": 300},
            self._on_find_part,
            self._on_find_error,
        )

    def _on_find_part(self, data):
        for item in data.get("items") or []:
            self._find_items.append(item)
        self._find_step()

    def _on_find(self, keyword, data):
        self.find_btn.setEnabled(True)
        items = data.get("items") or []
        # 名称搜索与数值扫描是两条独立流程，重置扫描次数避免「再次扫描」串到旧数据
        self.scans = 0
        self._render(items)
        text = "名称搜索「%s」：命中 %d 个变量" % (keyword, len(items))
        if not items:
            if data.get("store_size") == 0:
                text += ("。游戏当前没有任何存档变量（store 为 0），说明还停在主菜单/标题界面，"
                         "请先「开始游戏」或「读取存档」再搜索")
            else:
                text += ("，换个关键词试试（支持变量名、属性名、字典键名）。"
                         "游戏内的变量通常在「开始游戏 / 读取存档」后才创建，"
                         "主菜单下可能搜不到，先读档再搜")
        else:
            text += "，双击可直接修改"
        self.status.setText(text)
        self.ctrl.log(text)

    def _on_find_error(self, message):
        self.find_btn.setEnabled(True)
        self.ctrl.toast(message)

    def _reset(self):
        self.scans = 0
        self._items_all = []
        self._history = {}
        self.table.setRowCount(0)
        self.filter_hint.setText("")
        self.status.setText("已重置，请重新输入数值并「首次扫描」。")
        if self.ctrl.connected:
            self.ctrl.call("scan", {"value": "0", "mode": "reset"}, lambda _d: None, lambda _m: None)

    def _selected_path(self):
        row = self.table.currentRow()
        if row < 0:
            return ""
        return _path_of(self.table, row)

    def _selected_paths(self):
        """支持 Ctrl / Shift 多选；没有选中时退回当前行"""
        rows = sorted({index.row() for index in self.table.selectedIndexes()})
        paths = [_path_of(self.table, row) for row in rows]
        paths = [path for path in paths if path]
        if not paths:
            path = self._selected_path()
            if path:
                paths = [path]
        return paths

    def _batch_tip(self, paths):
        return "（共 %d 项）" % len(paths) if len(paths) > 1 else ""

    def _start_batch(self, kind, paths, text="", note=""):
        self._batch = {"kind": kind, "paths": list(paths), "text": text,
                       "note": note, "ok": 0, "fail": 0}
        self._batch_step()

    def _batch_step(self):
        batch = getattr(self, "_batch", None)
        if not batch:
            return
        if not batch["paths"]:
            status = "批量操作完成：成功 %d 项" % batch["ok"]
            if batch["fail"]:
                status += "，失败 %d 项" % batch["fail"]
            self.status.setText(status)
            self.ctrl.log(status)
            self._batch = None
            return
        path = batch["paths"].pop(0)
        kind = batch["kind"]
        on_error = (lambda message, p=path: self._batch_failed(p, message))
        if kind == "set":
            self.ctrl.call("get", {"path": path},
                           lambda data, p=path: self._batch_set(p, data),
                           on_error)
        elif kind == "freeze":
            self.ctrl.call("freeze", {"path": path},
                           lambda data, p=path: self._batch_froze(p, data),
                           on_error)
        else:
            self.ctrl.call("get", {"path": path},
                           lambda data, p=path: self._batch_record(p, data),
                           on_error)

    def _batch_failed(self, path, message):
        batch = getattr(self, "_batch", None)
        if batch:
            batch["fail"] += 1
        self.ctrl.log("批量操作失败 %s：%s" % (path, message))
        self._batch_step()

    def _batch_set(self, path, data):
        batch = self._batch
        before = str(data.get("value", ""))
        type_name = data.get("type", "")
        self.ctrl.call(
            "set",
            {"path": path, "value": batch["text"]},
            lambda result, p=path, b=before, t=type_name: self._batch_set_done(p, b, t, result),
            lambda message, p=path: self._batch_failed(p, message),
        )

    def _batch_set_done(self, path, before, type_name, result):
        self._batch["ok"] += 1
        self._after_set(path, result, before, type_name, select=False)
        self._batch_step()

    def _batch_froze(self, path, data):
        self._batch["ok"] += 1
        if self.ctrl.has_record(path):
            self.ctrl.update_record(path, frozen=True)
        else:
            self.ctrl.record_change(path, data.get("value"), data.get("value"), frozen=True)
        self.ctrl.log("已锁定 %s = %s" % (path, data.get("value")))
        self._batch_step()

    def _batch_record(self, path, data):
        self._batch["ok"] += 1
        self.ctrl.record_change(path, data.get("value"), "—", data.get("type", ""),
                                note=self._batch["note"])
        self._batch_step()

    def _edit_selected(self):
        paths = self._selected_paths()
        if not paths:
            self.ctrl.toast("请先在列表中选择要修改的变量")
            return
        if len(paths) > 1:
            preview = "\n".join(paths[:8])
            if len(paths) > 8:
                preview += "\n…还有 %d 项" % (len(paths) - 8)
            text, ok = QInputDialog.getText(
                self, "批量修改",
                "把选中的 %d 个变量都改成：\n%s\n\n新值：" % (len(paths), preview),
            )
            if ok and text.strip():
                self._start_batch("set", paths, text=text.strip())
            return
        path = paths[0]
        self.ctrl.call(
            "get",
            {"path": path},
            lambda data: self._show_editor(path, data),
            lambda message: QMessageBox.warning(self, "读取失败", message),
        )

    def _show_editor(self, path, data):
        before = str(data.get("value", ""))
        type_name = data.get("type", "")
        text, ok = QInputDialog.getText(
            self, "修改变量",
            "%s（%s）\n修改前：%s\n新值：" % (path, type_name, before),
            text=before,
        )
        if not ok:
            return
        self.ctrl.call(
            "set",
            {"path": path, "value": text},
            lambda result: self._after_set(path, result, before, type_name),
            lambda message: QMessageBox.warning(self, "修改失败", message),
        )

    def _on_double_click(self, index):
        if _note_cell(index):
            return
        self._edit_selected()

    def _after_set(self, path, result, before=None, type_name="", select=True):
        after = result.get("value")
        self.ctrl.log("已修改 %s：%s → %s" % (path, before, after))
        if before is None:
            self.ctrl.refresh_current()
            return
        # 保留这一行并标出「当前值 / 修改前」，不再自动再扫导致结果消失
        row = _row_of_path(self.table, path)
        if row >= 0:
            value_item = QTableWidgetItem(str(after))
            value_item.setToolTip(str(after))
            value_item.setForeground(Qt.GlobalColor.green)
            self.table.setItem(row, 3, value_item)
            before_item = QTableWidgetItem(str(before))
            before_item.setToolTip("修改前的值")
            self.table.setItem(row, 4, before_item)
            if select:
                self.table.selectRow(row)
        self.ctrl.record_change(path, before, after, type_name)
        if getattr(self, "_batch", None):
            return  # 批量修改时不逐条刷状态栏，最后统一汇总
        self.status.setText(
            "已修改 %s：%s → %s（已加入「修改记录」，可在该页随时再次修改或加备注）"
            % (path, before, after)
        )

    def _add_selected_to_records(self):
        paths = self._selected_paths()
        if not paths:
            self.ctrl.toast("请先在列表中选择一个变量")
            return
        if len(paths) > 1:
            note, ok = QInputDialog.getText(
                self, "批量加入修改记录",
                "把选中的 %d 个变量都加入记录，备注（可留空）：" % len(paths))
            if ok:
                self._start_batch("record", paths, note=note.strip())
            return
        path = paths[0]
        self.ctrl.call(
            "get",
            {"path": path},
            lambda data: self._confirm_add_record(path, data),
            lambda message: QMessageBox.warning(self, "读取失败", message),
        )

    def _confirm_add_record(self, path, data):
        if self.ctrl.has_record(path):
            note, ok = QInputDialog.getText(self, "修改备注", "%s 已在记录中，备注：" % path)
            if ok:
                self.ctrl.update_record(path, note=note.strip())
            return
        note, ok = QInputDialog.getText(self, "加入修改记录", "%s 的备注（可留空）：" % path)
        if not ok:
            return
        self.ctrl.record_change(path, data.get("value"), "—", data.get("type", ""), note=note.strip())
        self.ctrl.toast("已加入修改记录：" + path)

    def _on_context_menu(self, pos):
        index = self.table.indexAt(pos)
        if not index.isValid():
            return
        row = index.row()
        path = _path_of(self.table, row)
        if not path:
            return
        menu = QMenu(self)
        name_item = self.table.item(row, 0)
        type_item = self.table.item(row, 2)
        menu.addAction(self.favorite_action(
            path,
            name_item.text() if name_item else "",
            type_item.text() if type_item else "",
        ))
        menu.addSeparator()
        paths = self._selected_paths()
        suffix = self._batch_tip(paths)
        edit_action = QAction("修改值…" + suffix, self)
        edit_action.triggered.connect(self._edit_selected)
        record_action = QAction("加入修改记录…" + suffix, self)
        record_action.triggered.connect(self._add_selected_to_records)
        freeze_action = QAction("锁定此值" + suffix, self)
        freeze_action.triggered.connect(self._freeze_selected)
        copy_action = QAction("复制变量名", self)
        copy_action.triggered.connect(lambda: self.ctrl.copy_text(path))
        menu.addAction(edit_action)
        menu.addAction(record_action)
        menu.addAction(freeze_action)
        menu.addSeparator()
        menu.addAction(copy_action)
        menu.exec(self.table.viewport().mapToGlobal(pos))

    def _freeze_selected(self):
        paths = self._selected_paths()
        if not paths:
            self.ctrl.toast("请先在列表中选择一个变量")
            return
        if len(paths) > 1:
            self._start_batch("freeze", paths)
            return
        path = paths[0]
        self.ctrl.call(
            "freeze",
            {"path": path},
            lambda data: self._after_freeze(path, data),
            lambda message: QMessageBox.warning(self, "锁定失败", message),
        )

    def _after_freeze(self, path, data):
        self.ctrl.log("已锁定 %s = %s" % (path, data.get("value")))
        if self.ctrl.has_record(path):
            self.ctrl.update_record(path, frozen=True)
        else:
            self.ctrl.record_change(path, data.get("value"), data.get("value"), frozen=True)
        self.ctrl.toast("已锁定 %s" % path)


class FreezePage(BasePage):
    def __init__(self, ctrl):
        super().__init__(ctrl)
        self._busy = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        top = QHBoxLayout()
        tip = QLabel("锁定的数值会被持续写回游戏（类似 CE 的「锁定」），关闭游戏后失效。")
        tip.setObjectName("muted")
        refresh_btn = QPushButton("刷新")
        refresh_btn.clicked.connect(self.refresh)
        top.addWidget(tip, 1)
        top.addWidget(refresh_btn)
        layout.addLayout(top)

        self.table = make_table(["变量路径", "类型", "锁定值", "游戏当前值", "中文名"],
                                ctrl=self.ctrl)
        self.table.setColumnWidth(0, 280)
        self.table.setColumnWidth(1, 80)
        self.table.setColumnWidth(2, 140)
        self.table.setColumnWidth(4, 150)
        layout.addWidget(self.table, 1)

        bottom = QHBoxLayout()
        edit_btn = QPushButton("修改锁定值")
        edit_btn.clicked.connect(self._edit_lock)
        unfreeze_btn = QPushButton("解除选中")
        unfreeze_btn.clicked.connect(self._unfreeze_selected)
        clear_btn = QPushButton("全部解除")
        clear_btn.setObjectName("danger")
        clear_btn.clicked.connect(self._unfreeze_all)
        bottom.addStretch(1)
        bottom.addWidget(edit_btn)
        bottom.addWidget(unfreeze_btn)
        bottom.addWidget(clear_btn)
        layout.addLayout(bottom)

    def refresh(self):
        if not self.ctrl.connected or self._busy:
            return
        self._busy = True
        self.ctrl.call("frozen", {}, self._on_data, self._on_error)

    def _on_data(self, data):
        self._busy = False
        if not self.isVisible():
            return
        items = data.get("items") or []
        table = self.table
        table.setRowCount(len(items))
        for index, item in enumerate(items):
            path = item.get("path") or ""
            name_item = QTableWidgetItem(path)
            name_item.setData(Qt.ItemDataRole.UserRole, path)
            name_item.setToolTip(path)
            table.setItem(index, 0, name_item)
            table.setItem(index, 1, QTableWidgetItem(item.get("type") or ""))
            table.setItem(index, 2, QTableWidgetItem(item.get("value") or ""))
            table.setItem(index, 3, QTableWidgetItem(item.get("current") or ""))
            table.setItem(index, 4, cn_path_cell(path))

    def _on_error(self, _message):
        self._busy = False

    def _selected(self):
        row = self.table.currentRow()
        if row < 0:
            return "", ""
        path = _path_of(self.table, row)
        value_item = self.table.item(row, 2)
        return path, (value_item.text() if value_item else "")

    def _edit_lock(self):
        path, value = self._selected()
        if not path:
            self.ctrl.toast("请先选择一个锁定项")
            return
        text, ok = QInputDialog.getText(self, "修改锁定值", "%s 的锁定值：" % path, text=value)
        if not ok:
            return
        self.ctrl.call(
            "freeze",
            {"path": path, "value": text},
            lambda data: self._after_change(path, data),
            lambda message: QMessageBox.warning(self, "修改失败", message),
        )

    def _after_change(self, path, data):
        self.ctrl.log("已更新锁定 %s = %s" % (path, data.get("value")))
        self.refresh()

    def _unfreeze_selected(self):
        path, _ = self._selected()
        if not path:
            self.ctrl.toast("请先选择一个锁定项")
            return
        self.ctrl.call("unfreeze", {"path": path}, lambda data: self._after_unfreeze(path, data))

    def _after_unfreeze(self, path, _data):
        self.ctrl.log("已解除锁定 %s" % path)
        self.refresh()

    def _unfreeze_all(self):
        self.ctrl.call("unfreeze", {"all": True}, lambda _d: self.refresh())


class PersistentPage(BasePage):
    def __init__(self, ctrl):
        super().__init__(ctrl)
        self._busy = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        top = QHBoxLayout()
        tip = QLabel("persistent 数据会跨存档保存（例如已解锁内容、设置），修改前请先备份存档。")
        tip.setObjectName("muted")
        refresh_btn = QPushButton("刷新")
        refresh_btn.clicked.connect(self.refresh)
        top.addWidget(tip, 1)
        top.addWidget(refresh_btn)
        layout.addLayout(top)

        self.table = make_table(["变量名", "中文名", "类型", "当前值"], ctrl=self.ctrl)
        self.table.setColumnWidth(0, 250)
        self.table.setColumnWidth(1, 140)
        self.table.setColumnWidth(2, 80)
        self.table.doubleClicked.connect(self._on_double_click)
        layout.addWidget(self.table, 1)

    def poll_if_needed(self):
        pass

    def refresh(self):
        if not self.ctrl.connected or self._busy:
            return
        self._busy = True
        self.ctrl.call("list", {"scope": "persistent", "objects": True}, self._on_data, self._on_error)

    def _on_data(self, data):
        self._busy = False
        if not self.isVisible():
            return
        items = data.get("items") or []
        table = self.table
        table.setUpdatesEnabled(False)
        table.setRowCount(len(items))
        for index, item in enumerate(items):
            path = item.get("path") or ""
            raw_name = item.get("name") or path
            name_item = QTableWidgetItem(raw_name)
            name_item.setData(Qt.ItemDataRole.UserRole, path)
            name_item.setToolTip(path)
            table.setItem(index, 0, name_item)
            table.setItem(index, 1, cn_cell(raw_name, path))
            table.setItem(index, 2, QTableWidgetItem(item.get("type") or ""))
            value_item = QTableWidgetItem(item.get("value") or "")
            value_item.setToolTip(item.get("value") or "")
            table.setItem(index, 3, value_item)
        table.setUpdatesEnabled(True)

    def _on_error(self, _message):
        self._busy = False

    def _on_double_click(self, index):
        if _note_cell(index):
            return
        row = index.row()
        path = _path_of(self.table, row)
        if not path:
            return
        self.ctrl.call("get", {"path": path}, lambda data: self._show_editor(path, data),
                       lambda message: QMessageBox.warning(self, "读取失败", message))

    def _show_editor(self, path, data):
        before = str(data.get("value", ""))
        type_name = data.get("type", "")
        text, ok = QInputDialog.getText(
            self, "修改持久化数据",
            "%s（%s）\n修改前：%s\n新值：" % (path, type_name, before),
            text=before,
        )
        if not ok:
            return
        self.ctrl.call(
            "set",
            {"path": path, "value": text},
            lambda result: self._after_set(path, result, before, type_name),
            lambda message: QMessageBox.warning(self, "修改失败", message),
        )

    def _after_set(self, path, result, before=None, type_name=""):
        after = result.get("value")
        self.ctrl.log("已修改 %s：%s → %s" % (path, before, after))
        if before is not None:
            self.ctrl.record_change(path, before, after, type_name)
        self.refresh()


class CharacterPage(BasePage):
    """按角色名 / 变量名找到角色对象，列出可修改的属性"""

    def __init__(self, ctrl):
        super().__init__(ctrl)
        self._chars = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)
        label = QLabel("角色名 / 变量名")
        label.setObjectName("section")
        self.keyword_edit = QLineEdit()
        self.keyword_edit.setPlaceholderText("例如 Nora、特工、g_characters、nora（不区分大小写）")
        self.keyword_edit.setFixedWidth(300)
        self.keyword_edit.returnPressed.connect(self._search)
        self.search_btn = QPushButton("查找角色")
        self.search_btn.setObjectName("primary")
        self.search_btn.clicked.connect(self._search)
        self.search_btn.setEnabled(False)
        self.list_btn = QPushButton("列出全部角色")
        self.list_btn.clicked.connect(self._list_all)
        self.list_btn.setEnabled(False)
        toolbar.addWidget(label)
        toolbar.addWidget(self.keyword_edit)
        toolbar.addWidget(self.search_btn)
        toolbar.addWidget(self.list_btn)
        self.clean_box = QCheckBox("隐藏空值 / 内部字段")
        self.clean_box.setChecked(True)
        self.clean_box.setToolTip("隐藏值为空以及排序、测试这类存档内部字段，只留可改的数值")
        self.clean_box.toggled.connect(lambda _checked: self._show_selected_attrs())
        toolbar.addWidget(self.clean_box)
        toolbar.addStretch(1)
        layout.addLayout(toolbar)

        self.status = QLabel("已连接后输入角色名点「查找角色」；找到角色后，下方会列出它的全部可修改属性。")
        self.status.setObjectName("muted")
        layout.addWidget(self.status)

        self.char_table = make_table(["名称", "类型", "变量路径", "属性数", "中文名"],
                                     ctrl=self.ctrl)
        self.char_table.setColumnWidth(0, 170)
        self.char_table.setColumnWidth(1, 70)
        self.char_table.setColumnWidth(2, 280)
        self.char_table.setColumnWidth(3, 70)
        self.char_table.setColumnWidth(4, 140)
        self.char_table.setMaximumHeight(190)
        self.char_table.itemSelectionChanged.connect(self._show_selected_attrs)
        layout.addWidget(self.char_table)

        attr_bar = QHBoxLayout()
        attr_bar.setSpacing(8)
        self.attr_filter = QLineEdit()
        self.attr_filter.setPlaceholderText("筛选属性：英文名或中文名，如 opinion、魅力、金钱")
        self.attr_filter.setFixedWidth(300)
        self.attr_filter.textChanged.connect(self._render_attr_rows)
        query_btn = QPushButton("单个查询…")
        query_btn.setToolTip("按变量路径查询当前值，可先右键复制属性路径再粘贴")
        query_btn.clicked.connect(lambda: query_path(self))
        attr_bar.addWidget(self.attr_filter)
        attr_bar.addStretch(1)
        attr_bar.addWidget(query_btn)
        layout.addLayout(attr_bar)

        self.attr_table = make_table(["属性", "中文名", "类型", "当前值"], ctrl=self.ctrl)
        self.attr_table.setColumnWidth(0, 200)
        self.attr_table.setColumnWidth(1, 130)
        self.attr_table.setColumnWidth(2, 70)
        self.attr_table.setColumnWidth(3, 200)
        self.attr_table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.attr_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.attr_table.doubleClicked.connect(self._on_attr_double_click)
        self.attr_table.itemSelectionChanged.connect(self._update_attr_buttons)
        self.attr_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.attr_table.customContextMenuRequested.connect(self._on_attr_menu)
        copy_shortcut = QShortcut(QKeySequence(QKeySequence.StandardKey.Copy), self.attr_table)
        copy_shortcut.setContext(Qt.ShortcutContext.WidgetShortcut)
        copy_shortcut.activated.connect(self._copy_attr_cell)
        layout.addWidget(self.attr_table, 1)
        self.bind_find(self.keyword_edit, self.char_table, enter_jump=False)

        bottom = QHBoxLayout()
        self.attr_status = QLabel("")
        self.attr_status.setObjectName("muted")
        self.edit_btn = QPushButton("修改属性")
        self.edit_btn.clicked.connect(self._edit_attr)
        self.freeze_btn = QPushButton("锁定属性")
        self.freeze_btn.clicked.connect(self._freeze_attr)
        self.record_btn = QPushButton("加入记录")
        self.record_btn.clicked.connect(self._record_attr)
        for btn in (self.edit_btn, self.freeze_btn, self.record_btn):
            btn.setEnabled(False)
        bottom.addWidget(self.attr_status, 1)
        bottom.addWidget(self.record_btn)
        bottom.addWidget(self.edit_btn)
        bottom.addWidget(self.freeze_btn)
        layout.addLayout(bottom)

    def on_connection_changed(self, connected):
        self.search_btn.setEnabled(connected)
        self.list_btn.setEnabled(connected)
        for btn in (self.edit_btn, self.freeze_btn, self.record_btn):
            btn.setEnabled(connected and self._selected_attr() != "")
        if not connected:
            self.status.setText("未连接游戏：请先在左侧点「连接」再查找角色。")

    # ---- 查找 ----
    def _search(self):
        if not self.ctrl.connected:
            self.ctrl.toast("请先连接游戏")
            return
        keyword = self.keyword_edit.text().strip()
        if not keyword:
            self._list_all()
            return
        self.status.setText("正在查找「%s」…" % keyword)
        self.ctrl.call(
            "explore",
            {"keyword": keyword},
            lambda data: self._on_search(keyword, data),
            self._on_search_error,
        )

    def _list_all(self):
        if not self.ctrl.connected:
            self.ctrl.toast("请先连接游戏")
            return
        self.status.setText("正在读取角色列表…")
        self.ctrl.call(
            "explore",
            {"keyword": ""},
            lambda data: self._on_search("", data),
            self._on_search_error,
        )

    def _on_search_error(self, message):
        self.status.setText("查找失败：" + message)

    def _on_search(self, keyword, data):
        items = data.get("items") or []
        self._chars = items
        table = self.char_table
        table.setUpdatesEnabled(False)
        table.setRowCount(len(items))
        for index, item in enumerate(items):
            name_item = QTableWidgetItem(item.get("label") or item.get("path") or "")
            name_item.setData(Qt.ItemDataRole.UserRole, item.get("path") or "")
            name_item.setToolTip(item.get("path") or "")
            table.setItem(index, 0, name_item)
            table.setItem(index, 1, QTableWidgetItem(item.get("kind") or ""))
            raw_path = item.get("path") or ""
            path_item = QTableWidgetItem(raw_path)
            path_item.setToolTip(raw_path)
            table.setItem(index, 2, path_item)
            count_item = QTableWidgetItem(str(item.get("count", len(item.get("attrs") or []))))
            count_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            table.setItem(index, 3, count_item)
            table.setItem(index, 4, cn_path_cell(raw_path))
        table.setUpdatesEnabled(True)

        if items:
            if keyword:
                self.status.setText("「%s」找到 %d 个对象，选中后查看属性" % (keyword, len(items)))
            else:
                self.status.setText("共列出 %d 个角色，选中后查看属性" % len(items))
            table.selectRow(0)
            self._show_selected_attrs()
        else:
            if keyword:
                self.status.setText(
                    "「%s」没有找到。可试角色的游戏内显示名、英文/韩文名或变量名（如 nora、TB_Actor）。"
                    % keyword
                )
            else:
                self.status.setText("没有识别到角色表，可改用「变量列表」查看全部变量。")
            self.attr_table.setRowCount(0)
            self.attr_status.setText("")

    def _show_selected_attrs(self):
        row = self.char_table.currentRow()
        if row < 0 or row >= len(self._chars):
            self.attr_table.setRowCount(0)
            self._attrs_all = []
            self._current_char = None
            return
        item = self._chars[row]
        self._current_char = item
        attrs = item.get("attrs") or []
        clean = self.clean_box.isChecked()
        if clean:
            def keep(attr):
                if str(attr.get("value", "")) in ("", "None", "null"):
                    return False
                # 属性名可能带归属前缀（Interests.display_order），看最后一段
                leaf = (attr.get("name") or "").split(".")[-1].lower()
                return leaf not in CHAR_FIELD_INTERNAL

            attrs = [attr for attr in attrs if keep(attr)]
        self._attrs_all = attrs
        self._render_attr_rows()

    def _render_attr_rows(self):
        """按筛选框重建属性表；不重新向游戏请求数据"""
        attrs = list(getattr(self, "_attrs_all", []) or [])
        keyword = self.attr_filter.text().strip().lower()
        if keyword:
            def hit(attr):
                label = cn_label(attr.get("name")) or ""
                for text in (attr.get("name"), attr.get("path"),
                             label, attr.get("type")):
                    if keyword in str(text or "").lower():
                        return True
                return False

            attrs = [attr for attr in attrs if hit(attr)]
        self._shown_attrs = attrs
        table = self.attr_table
        table.setUpdatesEnabled(False)
        table.setRowCount(len(attrs))
        for index, attr in enumerate(attrs):
            raw_name = attr.get("name") or ""
            name_item = QTableWidgetItem(raw_name)
            name_item.setData(Qt.ItemDataRole.UserRole, attr.get("path") or "")
            name_item.setToolTip("%s\n%s" % (raw_name, attr.get("path") or ""))
            table.setItem(index, 0, name_item)
            table.setItem(index, 1, cn_cell(raw_name, attr.get("path") or ""))
            table.setItem(index, 2, QTableWidgetItem(attr.get("type") or ""))
            value_item = QTableWidgetItem(attr.get("value") or "")
            value_item.setToolTip(attr.get("path") or "")
            table.setItem(index, 3, value_item)
        table.setUpdatesEnabled(True)
        item = getattr(self, "_current_char", None) or {}
        total = len(item.get("attrs") or [])
        if keyword:
            count_text = "筛选出 %d 项（共 %d 项可改属性）" % (len(attrs), total)
        elif len(attrs) != total:
            count_text = "显示 %d 项数值（另有 %d 项空值 / 内部字段已隐藏）" % (
                len(attrs), total - len(attrs))
        else:
            count_text = "共 %d 个可改属性" % len(attrs)
        self.attr_status.setText(
            "%s（%s）· %s；双击修改，Ctrl / Shift 多选后可批量改、锁定、加入记录"
            % (item.get("label") or item.get("path"),
               item.get("kind") or "对象", count_text)
        )
        self._update_attr_buttons()

    def _update_attr_buttons(self):
        has_attr = bool(self._selected_attrs())
        enabled = self.ctrl.connected and has_attr
        for btn in (self.edit_btn, self.freeze_btn, self.record_btn):
            btn.setEnabled(enabled)

    # ---- 属性操作 ----
    def _selected_attrs(self):
        """当前选中的所有属性路径（Ctrl / Shift 可多选）"""
        rows = sorted({index.row() for index in self.attr_table.selectedIndexes()})
        paths = []
        for row in rows:
            item = self.attr_table.item(row, 0)
            path = item.data(Qt.ItemDataRole.UserRole) if item else ""
            if path:
                paths.append(path)
        return paths

    def _selected_attr(self):
        return self._path_at(self.attr_table.currentRow())

    def _path_at(self, row):
        if row < 0:
            return ""
        item = self.attr_table.item(row, 0)
        return item.data(Qt.ItemDataRole.UserRole) if item else ""

    def _on_attr_double_click(self, index):
        if _note_cell(index):
            return
        self._edit_attr()

    def _edit_attr(self):
        paths = self._selected_attrs()
        if not paths:
            self.ctrl.toast("请先选择一个属性")
            return
        if len(paths) > 1:
            value = self._attr_text(3)
            text, ok = QInputDialog.getText(
                self, "批量修改属性",
                "把选中的 %d 项设为：" % len(paths), text=value)
            if not ok or not text.strip():
                return
            target = text.strip()
            before = {}
            for attr in (getattr(self, "_attrs_all", []) or []):
                if attr.get("path") in paths:
                    before[attr.get("path")] = (attr.get("value"),
                                                attr.get("type") or "")
            self.ctrl.call(
                "affection_set",
                {"paths": paths, "value": target},
                lambda data: self._on_batch_attr_set(data, target, paths, before),
                self._on_batch_attr_error,
            )
            return
        path = paths[0]
        self.ctrl.call(
            "get",
            {"path": path},
            lambda data: self._show_attr_editor(path, data),
            lambda message: QMessageBox.warning(self, "读取失败", message),
        )

    def _on_batch_attr_set(self, data, target="", paths=None, before=None):
        changed = data.get("changed") or 0
        failed = data.get("failed") or []
        failed_paths = {item[0] for item in failed}
        # 本地缓存同步成新值，避免刷新后还显示旧数字
        for attr in (getattr(self, "_attrs_all", []) or []):
            path = attr.get("path")
            if path in (paths or []) and path not in failed_paths:
                attr["value"] = target
        for path in (paths or []):
            if path in failed_paths:
                continue
            old_value, type_name = (before or {}).get(path, ("", ""))
            self.ctrl.record_change(path, old_value, target, type_name)
        message = "已修改 %d 项" % changed
        if failed:
            message += "，%d 项失败（%s）" % (len(failed), failed[0][1] if failed else "")
        self.ctrl.log("批量修改属性：" + message)
        self.ctrl.toast(message)
        self._render_attr_rows()

    def _on_batch_attr_error(self, message):
        QMessageBox.warning(self, "修改失败", message)

    def _show_attr_editor(self, path, data):
        before = str(data.get("value", ""))
        type_name = data.get("type", "")
        text, ok = QInputDialog.getText(
            self, "修改属性",
            "%s（%s）\n修改前：%s\n新值：" % (path, type_name, before),
            text=before,
        )
        if not ok:
            return
        self.ctrl.call(
            "set",
            {"path": path, "value": text},
            lambda result: self._after_attr_set(path, result, before, type_name),
            lambda message: QMessageBox.warning(self, "修改失败", message),
        )

    def _after_attr_set(self, path, result, before, type_name):
        after = result.get("value")
        row = self.attr_table.currentRow()
        if row >= 0:
            value_item = QTableWidgetItem(str(after))
            value_item.setForeground(Qt.GlobalColor.green)
            value_item.setToolTip(path)
            self.attr_table.setItem(row, 3, value_item)
        self.ctrl.record_change(path, before, after, type_name)
        self.ctrl.log("已修改 %s：%s → %s" % (path, before, after))
        self.ctrl.toast("已修改 %s" % path)

    def _record_attr(self):
        rows = sorted({index.row() for index in self.attr_table.selectedIndexes()})
        if not rows:
            self.ctrl.toast("请先选择要记录的属性")
            return
        added = 0
        for row in rows:
            name_item = self.attr_table.item(row, 0)
            path = name_item.data(Qt.ItemDataRole.UserRole) if name_item else ""
            if not path or self.ctrl.has_record(path):
                continue
            value_item = self.attr_table.item(row, 3)
            type_item = self.attr_table.item(row, 2)
            value = value_item.text() if value_item else ""
            type_name = type_item.text() if type_item else ""
            self.ctrl.record_change(path, value, "—", type_name)
            added += 1
        if added:
            self.ctrl.toast("已加入修改记录 %d 项" % added)
        else:
            self.ctrl.toast("选中的属性都已在修改记录中")

    def _freeze_attr(self):
        if not self.ctrl.connected:
            self.ctrl.toast("请先连接游戏")
            return
        paths = self._selected_attrs()
        if not paths:
            self.ctrl.toast("请先选择一个属性")
            return
        for path in paths:
            self.ctrl.call(
                "freeze",
                {"path": path},
                lambda data, item_path=path: self._after_freeze(item_path, data),
                lambda message: QMessageBox.warning(self, "锁定失败", message),
            )
        self.ctrl.toast("已锁定 %d 项，可在「数值锁定」页解除" % len(paths))

    def _after_freeze(self, path, data):
        value = data.get("value")
        if self.ctrl.has_record(path):
            self.ctrl.update_record(path, frozen=True)
        else:
            self.ctrl.record_change(path, value, value, frozen=True)
        self.ctrl.log("已锁定 %s = %s" % (path, value))

    def _attr_text(self, column):
        return self._attr_text_at(self.attr_table.currentRow(), column)

    def _attr_text_at(self, row, column):
        if row < 0:
            return ""
        item = self.attr_table.item(row, column)
        return item.text() if item else ""

    def _copy_attr_cell(self):
        """Ctrl+C：复制当前单元格内容"""
        index = self.attr_table.currentIndex()
        if not index.isValid():
            return
        item = QTableWidget.item(self.attr_table, index.row(), index.column())
        if item is not None and item.text():
            self.ctrl.copy_text(item.text())

    def _on_attr_menu(self, pos):
        index = self.attr_table.indexAt(pos)
        if not index.isValid():
            return
        row = index.row()
        # 右键点在已选中的行上时保留多选，否则只选中这一行
        selected_rows = {idx.row() for idx in self.attr_table.selectedIndexes()}
        if row not in selected_rows:
            self.attr_table.selectRow(row)
        self._update_attr_buttons()
        paths = self._selected_attrs()
        menu = QMenu(self)
        if len(paths) > 1:
            edit_action = QAction("批量修改选中 %d 项…" % len(paths), self)
        else:
            edit_action = QAction("修改值…", self)
        edit_action.triggered.connect(self._edit_attr)
        record_action = QAction("加入修改记录…", self)
        record_action.triggered.connect(self._record_attr)
        freeze_action = QAction("锁定此值", self)
        freeze_action.triggered.connect(self._freeze_attr)
        copy_name = QAction("复制属性名", self)
        copy_name.triggered.connect(
            lambda: self.ctrl.copy_text(self._attr_text_at(row, 0)))
        copy_cn = QAction("复制中文名", self)
        copy_cn.triggered.connect(
            lambda: self.ctrl.copy_text(self._attr_text_at(row, 1)))
        copy_action = QAction("复制变量路径", self)
        copy_action.triggered.connect(
            lambda: self.ctrl.copy_text(self._path_at(row)))
        copy_value = QAction("复制当前值", self)
        copy_value.triggered.connect(
            lambda: self.ctrl.copy_text(self._attr_text_at(row, 3)))
        query_action = QAction("单个查询此属性", self)
        query_action.triggered.connect(
            lambda: query_path(self, self._path_at(row)))
        menu.addAction(self.favorite_action(
            self._path_at(row), self._attr_text_at(row, 0), self._attr_text_at(row, 2)))
        menu.addSeparator()
        menu.addAction(edit_action)
        menu.addAction(record_action)
        menu.addAction(freeze_action)
        menu.addSeparator()
        menu.addAction(copy_name)
        menu.addAction(copy_cn)
        menu.addAction(copy_action)
        menu.addAction(copy_value)
        if len(paths) > 1:
            copy_all = QAction("复制选中路径（%d 项）" % len(paths), self)
            copy_all.triggered.connect(
                lambda: self.ctrl.copy_text("\n".join(paths)))
            menu.addAction(copy_all)
        menu.addSeparator()
        menu.addAction(query_action)
        menu.exec(self.attr_table.viewport().mapToGlobal(pos))


class ItemAddDialog(QDialog):
    """从游戏物品表里挑一个物品并填数量"""

    def __init__(self, catalog, ctrl=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("添加物品")
        self.resize(720, 480)
        self._catalog = catalog
        self.ctrl = ctrl

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        top = QHBoxLayout()
        self.filter_edit = QLineEdit()
        self.filter_edit.setPlaceholderText("搜索物品名称或 ID…")
        self.filter_edit.textChanged.connect(self._apply_filter)
        top.addWidget(self.filter_edit, 1)
        top.addWidget(QLabel("数量"))
        self.count_spin = QSpinBox()
        self.count_spin.setRange(1, 9999)
        self.count_spin.setValue(1)
        self.count_spin.setFixedWidth(90)
        top.addWidget(self.count_spin)
        layout.addLayout(top)

        self.table = make_table(["名称", "物品 ID", "分类", "价格"], ctrl=self.ctrl)
        self.table.setColumnWidth(0, 260)
        self.table.setColumnWidth(1, 200)
        self.table.setColumnWidth(2, 70)
        self.table.setColumnWidth(3, 80)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.doubleClicked.connect(self.accept)
        self.table.itemSelectionChanged.connect(self._update_hint)
        layout.addWidget(self.table, 1)

        self.status = QLabel("")
        self.status.setObjectName("muted")
        layout.addWidget(self.status)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("添加选中")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._fill("")

    def _fill(self, keyword):
        rows = []
        for key, info in self._catalog.items():
            if keyword and keyword not in key.lower() and keyword not in (info.get("name") or "").lower():
                continue
            rows.append((info.get("name") or key, key, info.get("cate", ""), info.get("price", "")))
        rows.sort(key=lambda row: (row[2], row[0]))
        self.table.setUpdatesEnabled(False)
        self.table.setRowCount(len(rows))
        for index, (name, key, cate, price) in enumerate(rows):
            name_item = QTableWidgetItem(name)
            name_item.setData(Qt.ItemDataRole.UserRole, key)
            self.table.setItem(index, 0, name_item)
            self.table.setItem(index, 1, QTableWidgetItem(key))
            self.table.setItem(index, 2, QTableWidgetItem(str(cate)))
            self.table.setItem(index, 3, QTableWidgetItem(str(price)))
        self.table.setUpdatesEnabled(True)
        if rows:
            self.table.selectRow(0)
        self._update_hint()

    def _apply_filter(self):
        self._fill(self.filter_edit.text().strip().lower())

    def _update_hint(self):
        total = self.table.rowCount()
        picked = len(self.table.selectionModel().selectedRows())
        if picked > 1:
            self.status.setText(
                "已选 %d 个物品，点「添加选中」一次全部添加（共 %d 个）" % (picked, total))
        else:
            self.status.setText("共 %d 个物品 · 双击直接添加，按住 Ctrl / Shift 可多选" % total)

    def selections(self):
        """返回所有选中物品（多选），没有选中时退回当前行"""
        picked = []
        for index in self.table.selectionModel().selectedRows():
            item = self.table.item(index.row(), 0)
            if item is None:
                continue
            key = item.data(Qt.ItemDataRole.UserRole)
            if key:
                picked.append({"pKey": key, "count": self.count_spin.value()})
        if not picked:
            row = self.table.currentRow()
            item = self.table.item(row, 0) if row >= 0 else None
            key = item.data(Qt.ItemDataRole.UserRole) if item is not None else None
            if key:
                picked.append({"pKey": key, "count": self.count_spin.value()})
        return picked


class BatchCountDialog(QDialog):
    """批量改数量：设为固定值 / 增加 / 减少"""

    def __init__(self, picked, parent=None):
        super().__init__(parent)
        self.setWindowTitle("批量修改物品数量")
        self.setMinimumWidth(360)
        layout = QVBoxLayout(self)
        hint = QLabel("将对选中的 %d 种物品执行：" % picked)
        hint.setObjectName("muted")
        layout.addWidget(hint)

        form = QFormLayout()
        self.mode_box = QComboBox()
        self.mode_box.addItems(["设为固定值", "增加", "减少"])
        form.addRow("方式", self.mode_box)

        self.value_spin = QSpinBox()
        self.value_spin.setRange(0, 999999)
        self.value_spin.setValue(99)
        form.addRow("数量", self.value_spin)
        layout.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def mode(self):
        return self.mode_box.currentIndex()

    def value(self):
        return self.value_spin.value()


class ItemsPage(BasePage):
    """物品：读取背包与物品表，可直接添加物品"""

    def __init__(self, ctrl):
        super().__init__(ctrl)
        self._catalog = {}
        self._items = []
        self._add_queue = []
        self._added = []
        self._add_failed = []
        self._wallet_items = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        top = QHBoxLayout()
        self.filter_edit = QLineEdit()
        self.filter_edit.setPlaceholderText("过滤背包物品…")
        self.filter_edit.textChanged.connect(self._apply_filter)
        self.refresh_btn = QPushButton("刷新")
        self.refresh_btn.clicked.connect(self.refresh)
        self.add_btn = QPushButton("添加物品…")
        self.add_btn.setObjectName("primary")
        self.add_btn.clicked.connect(self._add_item)
        top.addWidget(self.filter_edit, 1)
        top.addWidget(self.refresh_btn)
        top.addWidget(self.add_btn)
        layout.addLayout(top)

        # 我的数据：自动识别游戏金币 / 货币 / 玩家属性，中文名直接改
        wallet_box = QFrame()
        wallet_box.setObjectName("card")
        wallet_layout = QVBoxLayout(wallet_box)
        wallet_layout.setContentsMargins(10, 8, 10, 8)
        wallet_layout.setSpacing(6)
        wallet_head = QHBoxLayout()
        wallet_head.setSpacing(8)
        wallet_title = QLabel("我的数据 · 金币 / 属性")
        wallet_title.setObjectName("section")
        self.wallet_hint = QLabel("连接游戏后自动识别金币、钻石、体力、等级等数值。")
        self.wallet_hint.setObjectName("muted")
        self.wallet_edit_btn = QPushButton("修改数值…")
        self.wallet_edit_btn.clicked.connect(self._edit_wallet)
        self.wallet_edit_btn.setEnabled(False)
        wallet_head.addWidget(wallet_title)
        wallet_head.addSpacing(6)
        wallet_head.addWidget(self.wallet_hint, 1)
        wallet_head.addWidget(self.wallet_edit_btn)
        wallet_layout.addLayout(wallet_head)

        self.wallet_table = make_table(["名称", "当前值"], ctrl=self.ctrl)
        self.wallet_table.setColumnWidth(0, 260)
        self.wallet_table.setColumnWidth(1, 160)
        self.wallet_table.setMaximumHeight(170)
        self.wallet_table.doubleClicked.connect(
            lambda index: None if _note_cell(index) else self._edit_wallet())
        wallet_layout.addWidget(self.wallet_table)
        layout.addWidget(wallet_box)

        self.table = make_table(["物品名称", "数量", "物品 ID", "分类", "变量路径"], ctrl=self.ctrl)
        self.table.setColumnWidth(0, 230)
        self.table.setColumnWidth(1, 70)
        self.table.setColumnWidth(2, 190)
        self.table.setColumnWidth(3, 60)
        self.table.setColumnWidth(4, 180)
        self.table.doubleClicked.connect(self._edit_count)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.itemSelectionChanged.connect(self._update_buttons)
        layout.addWidget(self.table, 1)
        self.bind_find(self.filter_edit, self.table)

        bottom = QHBoxLayout()
        self.status = QLabel("连接游戏并进入存档后点「刷新」，这里会显示背包里的物品。")
        self.status.setObjectName("muted")
        self.batch_btn = QPushButton("批量修改数量…")
        self.batch_btn.setToolTip("按住 Ctrl / Shift 多选物品，或在表内按 Ctrl+A 全选")
        self.batch_btn.clicked.connect(self._batch_edit_count)
        self.set_btn = QPushButton("修改数量…")
        self.set_btn.clicked.connect(self._edit_count)
        self.record_btn = QPushButton("加入记录")
        self.record_btn.clicked.connect(self._record_item)
        for btn in (self.batch_btn, self.set_btn, self.record_btn):
            btn.setEnabled(False)
        bottom.addWidget(self.status, 1)
        bottom.addWidget(self.record_btn)
        bottom.addWidget(self.batch_btn)
        bottom.addWidget(self.set_btn)
        layout.addLayout(bottom)

    def on_connection_changed(self, connected):
        for btn in (self.refresh_btn, self.add_btn, self.set_btn, self.record_btn):
            btn.setEnabled(connected)
        if not connected:
            self.batch_btn.setEnabled(False)
            self.status.setText("未连接游戏：请先在左侧点「连接」再查看物品。")
            self.wallet_hint.setText("未连接游戏：连接后自动识别金币 / 属性。")
            self.wallet_table.setRowCount(0)
            self._wallet_items = []
            self.wallet_edit_btn.setEnabled(False)

    def refresh(self):
        if not self.ctrl.connected:
            self.ctrl.toast("请先连接游戏")
            return
        self.ctrl.call("items", {}, self._on_items, self._on_error)
        self._load_wallet()

    def _on_error(self, message):
        self.status.setText("读取物品失败：" + message)

    def _on_items(self, data):
        self._catalog = data.get("catalog") or {}
        self._items = data.get("inventory") or []
        table = self.table
        table.setUpdatesEnabled(False)
        table.setRowCount(len(self._items))
        for index, item in enumerate(self._items):
            name_item = QTableWidgetItem(item.get("name") or item.get("pKey") or "")
            name_item.setToolTip(item.get("desc") or "")
            name_item.setData(Qt.ItemDataRole.UserRole, item.get("path") or "")
            table.setItem(index, 0, name_item)
            count_item = QTableWidgetItem(str(item.get("count", "")))
            count_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            table.setItem(index, 1, count_item)
            table.setItem(index, 2, QTableWidgetItem(item.get("pKey") or ""))
            table.setItem(index, 3, QTableWidgetItem(str(item.get("cate", ""))))
            path_item = QTableWidgetItem(item.get("path") or "")
            table.setItem(index, 4, path_item)
        table.setUpdatesEnabled(True)
        self._apply_filter()

        if self._items:
            text = ("背包 %d 种物品（上限 %s）· 双击数量可改，Ctrl / Shift 多选可批量修改"
                    % (len(self._items), data.get("max_slot") or "?"))
            language = str(data.get("language") or "None")
            i18n_count = int(data.get("i18n") or 0)
            if i18n_count:
                text += " · 中文对照 %d 条" % i18n_count
            elif "chinese" not in language:
                text += " · 该游戏没有中文翻译脚本，名称显示数据表原文"
            self.status.setText(text)
        else:
            if not self._catalog:
                self.status.setText(
                    "这个游戏没有标准的物品表 / 背包结构，物品页用不上；"
                    "可以直接在「数值搜索」里按名称查变量。")
            else:
                self.status.setText(
                    "背包里没有物品（已识别 %d 种可添加道具）。若刚启动游戏，请先读档再点「刷新」；"
                    "也可以点右上角「添加物品…」直接添加。" % len(self._catalog))
        self._update_buttons()

    def _update_buttons(self):
        enabled = self.ctrl.connected and bool(self._items)
        selected = len(self._selected_items())
        for btn in (self.set_btn, self.record_btn):
            btn.setEnabled(enabled)
        self.batch_btn.setEnabled(enabled and selected > 0)
        self.wallet_edit_btn.setEnabled(self.ctrl.connected and bool(self._wallet_items))

    # ---- 我的数据：金币 / 货币 / 玩家属性 ----
    def _load_wallet(self):
        if not self.ctrl.connected:
            return
        self.wallet_hint.setText("正在识别金币 / 属性…")
        self.ctrl.call("wallet", {}, self._on_wallet,
                       lambda message: self.wallet_hint.setText("识别失败：" + message))

    def _on_wallet(self, data):
        items = data.get("items") or []
        picked = []
        index_by_label = {}
        # 保持服务端顺序（资源在前），同一中文名只留路径最短的那条
        for entry in items:
            label = _cn_attr_label(entry)
            if not label:
                continue
            position = index_by_label.get(label)
            if position is None:
                index_by_label[label] = len(picked)
                picked.append((label, entry))
            elif len(entry.get("path") or "") < len(picked[position][1].get("path") or ""):
                picked[position] = (label, entry)
        picked = picked[:20]
        self._wallet_items = [entry for _label, entry in picked]

        table = self.wallet_table
        table.setUpdatesEnabled(False)
        table.setRowCount(len(picked))
        for row, (label, entry) in enumerate(picked):
            name_item = QTableWidgetItem(label)
            name_item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            table.setItem(row, 0, name_item)
            value_item = QTableWidgetItem(str(entry.get("value", "")))
            value_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            value_item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            table.setItem(row, 1, value_item)
        table.setUpdatesEnabled(True)

        if picked:
            self.wallet_hint.setText("已识别 %d 项 · 双击数值直接修改，改完在游戏里存档"
                                     % len(picked))
        else:
            self.wallet_hint.setText(
                "暂未识别到金币 / 属性数值：进入游戏或读取存档后点「刷新」再试。")
        self._update_buttons()

    def _edit_wallet(self):
        row = self.wallet_table.currentRow()
        if row < 0 or row >= len(self._wallet_items):
            self.ctrl.toast("请先选择一个数值")
            return
        entry = self._wallet_items[row]
        label = self.wallet_table.item(row, 0).text()
        current = str(entry.get("value", ""))
        text, ok = QInputDialog.getText(
            self, "修改数值", "%s\n当前值：%s\n新值：" % (label, current), text=current)
        if not ok:
            return
        path = entry.get("path") or ""
        self.ctrl.call(
            "set", {"path": path, "value": text},
            lambda result: self._after_wallet_set(entry, label, current, result),
            lambda message: QMessageBox.warning(self, "修改失败", message),
        )

    def _after_wallet_set(self, entry, label, before, result):
        after = result.get("value")
        self.ctrl.log("已修改 %s：%s → %s" % (label, before, after))
        self.ctrl.record_change(entry.get("path") or "", before, after,
                                entry.get("type") or "")
        self._load_wallet()

    def _apply_filter(self):
        keyword = self.filter_edit.text().strip().lower()
        for row in range(self.table.rowCount()):
            name_item = self.table.item(row, 0)
            key_item = self.table.item(row, 2)
            text = ((name_item.text() if name_item else "") + " "
                    + (key_item.text() if key_item else "")).lower()
            self.table.setRowHidden(row, bool(keyword) and keyword not in text)

    def _selected_item(self):
        row = self.table.currentRow()
        if row < 0 or row >= len(self._items):
            return None
        return self._items[row]

    def _selected_items(self):
        """多选：返回选中的所有物品（按行号升序）"""
        rows = sorted({index.row() for index in
                       self.table.selectionModel().selectedRows()})
        return [self._items[row] for row in rows if 0 <= row < len(self._items)]

    # ---- 批量修改数量 ----
    def _batch_edit_count(self):
        picks = self._selected_items()
        if not picks:
            self.ctrl.toast("请先选中物品（Ctrl / Shift 多选，表内 Ctrl+A 全选）")
            return
        dialog = BatchCountDialog(len(picks), self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        mode, amount = dialog.mode(), dialog.value()
        queue = []
        skipped = 0
        for item in picks:
            try:
                current = int(item.get("count"))
            except (TypeError, ValueError):
                skipped += 1
                continue
            if mode == 0:
                target = amount
            elif mode == 1:
                target = current + amount
            else:
                target = current - amount
                if target < 0:
                    target = 0
            queue.append((item, current, target))
        if not queue:
            self.ctrl.toast("选中的物品数量不是数字，无法批量修改")
            return
        self._batch_queue = queue
        self._batch_skipped = skipped
        self._batch_done = 0
        self._batch_failed = 0
        self._batch_next()

    def _batch_next(self):
        if not self._batch_queue:
            text = "已修改 %d 种物品数量" % self._batch_done
            if self._batch_failed:
                text += "，%d 种失败" % self._batch_failed
            if self._batch_skipped:
                text += "，%d 种数量非数字已跳过" % self._batch_skipped
            self.ctrl.toast(text)
            self.refresh()
            return
        item, before, target = self._batch_queue.pop(0)
        self.ctrl.call(
            "set",
            {"path": item.get("path"), "value": str(target), "value_type": "int"},
            lambda result, it=item, old=before: self._after_batch_set(it, old, result),
            lambda message, it=item: self._after_batch_failed(it, message),
        )

    def _after_batch_set(self, item, before, result):
        self._batch_done += 1
        self.ctrl.log("物品数量 %s：%s → %s" % (item.get("name"), before, result.get("value")))
        self.ctrl.record_change(item.get("path"), before, result.get("value"), "int",
                                note=item.get("name") or "")
        self._batch_next()

    def _after_batch_failed(self, item, message):
        self._batch_failed += 1
        self.ctrl.log("[错误] 批量修改 %s 失败：%s" % (item.get("name"), message))
        self._batch_next()

    def _edit_count(self, *_args):
        if _args and _note_cell(_args[0]):
            return
        item = self._selected_item()
        if not item:
            self.ctrl.toast("请先选择一个物品")
            return
        current = str(item.get("count", ""))
        text, ok = QInputDialog.getText(
            self, "修改物品数量",
            "%s（%s）\n当前数量：%s\n新数量：" % (item.get("name"), item.get("pKey"), current),
            text=current,
        )
        if not ok:
            return
        self.ctrl.call(
            "set",
            {"path": item.get("path"), "value": text, "value_type": "int"},
            lambda result: self._after_count(item, result),
            lambda message: QMessageBox.warning(self, "修改失败", message),
        )

    def _after_count(self, item, result):
        self.ctrl.log("物品数量 %s → %s" % (item.get("pKey"), result.get("value")))
        self.ctrl.record_change(item.get("path"), item.get("count"), result.get("value"), "int",
                                note=item.get("name") or "")
        self.refresh()

    def _record_item(self):
        item = self._selected_item()
        if not item:
            self.ctrl.toast("请先选择一个物品")
            return
        if self.ctrl.has_record(item.get("path")):
            self.ctrl.toast("该物品数量已在修改记录中")
            return
        self.ctrl.record_change(item.get("path"), item.get("count"), "—", "int",
                                note=item.get("name") or "")
        self.ctrl.toast("已加入修改记录：%s" % item.get("name"))

    def _add_item(self):
        if not self.ctrl.connected:
            self.ctrl.toast("请先连接游戏")
            return
        if not self._catalog:
            self.refresh()
            self.ctrl.toast("物品表还在读取，稍等后再点一次")
            return
        dialog = ItemAddDialog(self._catalog, self.ctrl, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        picks = dialog.selections()
        if not picks:
            self.ctrl.toast("请选择要添加的物品")
            return
        self._add_queue = list(picks)
        self._added = []
        self._add_failed = []
        self._add_next()

    def _add_next(self):
        """逐个提交选中物品，全部加完后统一刷新"""
        if not self._add_queue:
            if self._add_failed:
                self.ctrl.toast("已添加 %d 种物品，%d 种失败"
                                % (len(self._added), len(self._add_failed)))
            elif len(self._added) == 1:
                self.ctrl.toast("已添加 %s，当前数量 %s" % self._added[0])
            elif self._added:
                self.ctrl.toast("已添加 %d 种物品" % len(self._added))
            self.refresh()
            return
        pick = self._add_queue.pop(0)
        self.ctrl.call(
            "add_item",
            pick,
            lambda data, p=pick: self._after_add(p, data),
            lambda message, p=pick: self._after_add_failed(p, message),
        )

    def _after_add(self, pick, data):
        name = data.get("name") or data.get("pKey")
        self._added.append((name, data.get("count")))
        self.ctrl.log("添加物品 %s x%s（当前 %s）"
                      % (name, data.get("added"), data.get("count")))
        self._add_next()

    def _after_add_failed(self, pick, message):
        self._add_failed.append(pick.get("pKey"))
        self.ctrl.log("[错误] 添加 %s 失败：%s" % (pick.get("pKey"), message))
        if len(self._add_queue) == 0 and len(self._added) == 0:
            QMessageBox.warning(self, "添加失败", message)
        self._add_next()


class CollectPage(BasePage):
    """画廊 / 回忆 / 收集：自动识别各游戏的解锁标记并一键解锁"""

    def __init__(self, ctrl):
        super().__init__(ctrl)
        self._busy = False
        self._items = []
        self._groups = []
        self._group_filter = ""

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)
        self.filter_edit = QLineEdit()
        self.filter_edit.setPlaceholderText("按名称过滤，如 gallery / gallery_01 / 回忆")
        self.filter_edit.setFixedWidth(260)
        self.filter_edit.returnPressed.connect(self.refresh)
        self.all_box = QCheckBox("包含全部布尔变量")
        self.all_box.setToolTip("默认只识别解锁 / 画廊 / 回忆 / 特典 / 服装 等关键词的标记")
        self.all_box.stateChanged.connect(lambda _: self.refresh())
        scan_btn = QPushButton("扫描收集项")
        scan_btn.clicked.connect(self.refresh)
        self.unlock_btn = QPushButton("一键解锁全部")
        self.unlock_btn.clicked.connect(self._unlock_all)
        self.undo_btn = QPushButton("撤销上次解锁")
        self.undo_btn.clicked.connect(self._undo)
        toolbar.addWidget(self.filter_edit)
        toolbar.addWidget(self.all_box)
        toolbar.addStretch(1)
        toolbar.addWidget(scan_btn)
        toolbar.addWidget(self.unlock_btn)
        toolbar.addWidget(self.undo_btn)
        layout.addLayout(toolbar)

        self.group_table = make_table(["分组", "已解锁", "总数"], ctrl=self.ctrl)
        self.group_table.setColumnWidth(0, 260)
        self.group_table.setColumnWidth(1, 80)
        self.group_table.setColumnWidth(2, 80)
        self.group_table.setMaximumHeight(150)
        self.group_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.group_table.itemSelectionChanged.connect(self._on_group_selected)
        layout.addWidget(self.group_table)

        self.table = make_table(["变量路径", "类型", "当前值", "中文名"], ctrl=self.ctrl)
        self.table.setColumnWidth(0, 300)
        self.table.setColumnWidth(1, 80)
        self.table.setColumnWidth(3, 150)
        self.table.doubleClicked.connect(self._on_double_click)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._on_context_menu)
        layout.addWidget(self.table, 1)

        self.status = QLabel("点「扫描收集项」自动识别画廊 / 回忆 / CG 等解锁标记，再点「一键解锁全部」。")
        self.status.setObjectName("muted")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.bind_find(self.filter_edit, self.table, enter_jump=False)

    # ---- 生命周期 ----
    def refresh(self):
        if not self.ctrl.connected or self._busy:
            return
        self._busy = True
        self.status.setText("正在扫描解锁标记…")
        payload = {"include_all": self.all_box.isChecked(),
                   "keyword": self.filter_edit.text().strip()}
        self.ctrl.call("collect", payload, self._on_collect, self._on_error)

    def on_connection_changed(self, connected):
        self.unlock_btn.setEnabled(connected)
        self.undo_btn.setEnabled(connected)

    def _on_error(self, message):
        self._busy = False
        self.status.setText("扫描失败：" + message)

    def _on_collect(self, data):
        self._busy = False
        self._items = data.get("items") or []
        self._groups = data.get("groups") or []
        self._group_filter = ""
        self._render_groups()
        self._render_items()
        total = data.get("total") or 0
        unlocked = data.get("unlocked") or 0
        description = ("共识别 %d 个收集项，已解锁 %d，未解锁 %d。"
                       "双击单项可切换，右键可单独解锁；点击上方分组可只看该组。"
                       % (total, unlocked, total - unlocked))
        if total == 0:
            description = ("没有识别到收集项。可勾选「包含全部布尔变量」再扫一次；"
                           "若游戏用存档内数组记录画廊，请到「数值搜索」按名称查。")
        self.status.setText(description + " 解锁后记得在游戏里存档，才会永久保存。")
        self.ctrl.log("收集扫描：%d 项，未解锁 %d" % (total, total - unlocked))

    def _render_groups(self):
        self.group_table.blockSignals(True)
        self.group_table.setRowCount(0)
        for group in self._groups:
            row = self.group_table.rowCount()
            self.group_table.insertRow(row)
            name_item = QTableWidgetItem(str(group.get("name")))
            name_item.setData(Qt.ItemDataRole.UserRole, group.get("name"))
            self.group_table.setItem(row, 0, name_item)
            unlocked = group.get("unlocked") or 0
            total = group.get("total") or 0
            done = unlocked >= total and total > 0
            count_item = QTableWidgetItem("%d/%d" % (unlocked, total))
            count_item.setForeground(Qt.GlobalColor.green if done else Qt.GlobalColor.yellow)
            self.group_table.setItem(row, 1, count_item)
            self.group_table.setItem(row, 2, QTableWidgetItem(str(total)))
        self.group_table.blockSignals(False)

    def _render_items(self):
        items = self._items
        if self._group_filter:
            items = [item for item in items if item.get("group") == self._group_filter]
        self.table.setRowCount(0)
        for entry in items[:1500]:
            row = self.table.rowCount()
            self.table.insertRow(row)
            path_item = QTableWidgetItem(str(entry.get("path")))
            path_item.setData(Qt.ItemDataRole.UserRole, entry.get("path"))
            path_item.setToolTip(str(entry.get("name")))
            self.table.setItem(row, 0, path_item)
            self.table.setItem(row, 1, QTableWidgetItem(str(entry.get("type"))))
            value_item = QTableWidgetItem(str(entry.get("value")))
            if entry.get("container"):
                value_item.setForeground(Qt.GlobalColor.cyan)
            elif entry.get("unlocked"):
                value_item.setForeground(Qt.GlobalColor.green)
            else:
                value_item.setForeground(Qt.GlobalColor.gray)
            self.table.setItem(row, 2, value_item)
            self.table.setItem(row, 3, cn_path_cell(str(entry.get("path"))))

    def _on_group_selected(self):
        rows = self.group_table.selectionModel().selectedRows()
        if not rows:
            return
        item = self.group_table.item(rows[0].row(), 0)
        if item is None:
            return
        self._group_filter = item.data(Qt.ItemDataRole.UserRole) or ""
        self._render_items()

    # ---- 操作 ----
    def _locked_paths(self):
        paths = []
        for entry in self._items:
            if entry.get("container"):
                if (entry.get("unlocked") or 0) < (entry.get("total") or 0):
                    paths.append(entry.get("path"))
            elif not entry.get("unlocked"):
                paths.append(entry.get("path"))
        return [path for path in paths if path]

    def _unlock_all(self):
        if not self.ctrl.connected:
            self.ctrl.toast("请先连接游戏")
            return
        if not self._items:
            self.ctrl.toast("请先点「扫描收集项」")
            return
        paths = self._locked_paths()
        if not paths:
            self.ctrl.toast("没有未解锁的收集项")
            return
        answer = QMessageBox.question(
            self, "一键解锁",
            "将解锁 %d 个收集项（画廊 / 回忆 / CG 等）。\n"
            "解锁后可在「游戏内」打开画廊确认，记得存档才会永久保存。\n\n继续？" % len(paths))
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.status.setText("正在解锁 %d 项…" % len(paths))
        self.ctrl.call("unlock_all", {"paths": paths}, self._on_unlocked, self._on_error)

    def _on_unlocked(self, data):
        changed = data.get("changed") or 0
        failed = data.get("failed") or []
        message = "已解锁 %d 项" % changed
        if failed:
            message += "，%d 项失败（%s）" % (len(failed), failed[0][1] if failed else "")
        self.status.setText(message + "。现在可在游戏内打开画廊 / 回忆确认；需要撤销请点「撤销上次解锁」。")
        self.ctrl.log("一键解锁：" + message)
        self.refresh()

    def _undo(self):
        if not self.ctrl.connected:
            return
        self.ctrl.call("unlock_undo", {}, self._on_undo, self._on_error)

    def _on_undo(self, data):
        restored = data.get("restored") or 0
        self.status.setText("已撤销上次解锁，恢复 %d 项。" % restored)
        self.ctrl.log("撤销解锁：恢复 %d 项" % restored)
        self.refresh()

    def _selected_path(self):
        row = self.table.currentRow()
        if row < 0:
            return ""
        return _path_of(self.table, row)

    def _toggle_bool(self, row):
        path = _path_of(self.table, row)
        if not path:
            return
        value_item = self.table.item(row, 2)
        current = value_item.text().strip().lower() if value_item else ""
        target = "False" if current in ("true", "1") else "True"
        self.ctrl.call("set", {"path": path, "value": target},
                       lambda data: self._after_toggle(path, data),
                       lambda message: self.ctrl.toast("修改失败：" + message))

    def _after_toggle(self, path, data):
        self.ctrl.log("切换 %s = %s" % (path, data.get("value")))
        self.refresh()

    def _on_double_click(self, index):
        if _note_cell(index):
            return
        self._toggle_bool(index.row())

    def _on_context_menu(self, pos):
        row = self.table.currentRow()
        path = _path_of(self.table, row) if row >= 0 else ""
        if not path:
            return
        menu = QMenu(self)
        unlock_action = QAction("解锁该项", self)
        unlock_action.triggered.connect(lambda: self._unlock_one(path, True))
        lock_action = QAction("设为未解锁", self)
        lock_action.triggered.connect(lambda: self._unlock_one(path, False))
        copy_action = QAction("复制变量路径", self)
        copy_action.triggered.connect(lambda: self.ctrl.copy_text(path))
        menu.addAction(unlock_action)
        menu.addAction(lock_action)
        menu.addSeparator()
        menu.addAction(copy_action)
        menu.exec(self.table.viewport().mapToGlobal(pos))

    def _unlock_one(self, path, value):
        self.ctrl.call("set", {"path": path, "value": "True" if value else "False"},
                       lambda data: self._after_toggle(path, data),
                       lambda message: self.ctrl.toast("修改失败：" + message))


class AffectionPage(BasePage):
    """属性 / 关系值：自动识别角色属性、资源、等级等并批量修改"""

    def __init__(self, ctrl):
        super().__init__(ctrl)
        self._busy = False
        self._items = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)
        self.filter_edit = QLineEdit()
        self.filter_edit.setPlaceholderText("按角色 / 变量名过滤，如 nora、money、等级")
        self.filter_edit.setFixedWidth(260)
        self.filter_edit.textChanged.connect(self._render_items)
        self.group_box = QComboBox()
        self.group_box.setFixedWidth(130)
        self.group_box.addItem("全部分类", "")
        for name in ("好感 · 关系", "角色状态", "资源 · 货币", "等级 · 成长"):
            self.group_box.addItem(name, name)
        self.group_box.currentIndexChanged.connect(self._render_items)
        scan_btn = QPushButton("扫描属性")
        scan_btn.setObjectName("primary")
        scan_btn.clicked.connect(self.refresh)
        query_btn = QPushButton("单个查询…")
        query_btn.setToolTip("按变量路径查询当前值，可先右键复制属性路径再粘贴")
        query_btn.clicked.connect(lambda: query_path(self))
        self.set_btn = QPushButton("设为…")
        self.set_btn.clicked.connect(lambda: self._set_value())
        self.freeze_btn = QPushButton("锁定当前值")
        self.freeze_btn.clicked.connect(lambda: self._freeze())
        toolbar.addWidget(self.filter_edit)
        toolbar.addWidget(self.group_box)
        toolbar.addStretch(1)
        toolbar.addWidget(query_btn)
        toolbar.addWidget(scan_btn)
        toolbar.addWidget(self.set_btn)
        toolbar.addWidget(self.freeze_btn)
        layout.addLayout(toolbar)

        self.table = make_table(["分类", "角色", "属性", "中文名", "类型", "当前值", "位置"],
                                ctrl=self.ctrl)
        self.table.setColumnWidth(0, 90)
        self.table.setColumnWidth(1, 110)
        self.table.setColumnWidth(2, 190)
        self.table.setColumnWidth(3, 130)
        self.table.setColumnWidth(4, 70)
        self.table.setColumnWidth(5, 90)
        self.table.setColumnWidth(6, 70)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.doubleClicked.connect(self._on_double_click)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._on_context_menu)
        layout.addWidget(self.table, 1)

        self.status = QLabel(
            "点「扫描属性」自动识别好感关系、角色状态、资源货币、等级成长四类数值，"
            "覆盖变量名（nora_affection）、列表（g_amelia_heart）、"
            "角色表 / 角色对象字段（gd_InventoryActor.melissa.love）、统计表（stats.corruption）等存法。\n"
            "建议先进入游戏或读取存档再扫描，未开局时部分变量还没生成。"
            "双击修改单个，选中多行点「设为…」批量改；改完在游戏里存档或重进菜单生效。"
        )
        self.status.setObjectName("muted")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.bind_find(self.filter_edit, self.table)

    # ---- 生命周期 ----
    def refresh(self):
        if not self.ctrl.connected or self._busy:
            return
        self._busy = True
        self.status.setText("正在扫描好感度…")
        self.ctrl.call("affection", {}, self._on_scan, self._on_error)

    def on_connection_changed(self, connected):
        self.set_btn.setEnabled(connected)
        self.freeze_btn.setEnabled(connected)
        if connected:
            self.refresh()

    def _on_error(self, message):
        self._busy = False
        self.status.setText("扫描失败：" + message)

    def _on_scan(self, data):
        self._busy = False
        self._items = data.get("items") or []
        self._render_items()
        total = data.get("total") or 0
        if total:
            groups = {}
            for item in self._items:
                name = item.get("group") or "其他数值"
                groups[name] = groups.get(name, 0) + 1
            summary = "、".join("%s %d" % (name, count) for name, count in groups.items())
            names = sorted({item.get("character") for item in self._items})
            self.status.setText("识别到 %d 项（%s），涉及 %d 个角色 / 分组。"
                               "双击修改，或选中多行点「设为…」批量改。"
                               % (total, summary, len(names)))
        else:
            self.status.setText(
                "没有识别到属性数值：这款游戏可能用了别的叫法，"
                "可在「数值搜索」里按属性名搜，或在「角色属性」里找到角色后直接改属性。")
        self.ctrl.log("属性扫描：%d 项" % total)

    def _render_items(self):
        keyword = self.filter_edit.text().strip().lower()
        group = self.group_box.currentData() or ""
        items = self._items
        if group:
            items = [item for item in items if item.get("group") == group]
        if keyword:
            def hit(item):
                label = cn_label(item.get("name")) or ""
                for text in (item.get("character"), item.get("path"),
                             item.get("name"), item.get("group"), label):
                    if keyword in str(text or "").lower():
                        return True
                return False

            items = [item for item in items if hit(item)]
        self.table.setRowCount(0)
        for entry in items[:1800]:
            row = self.table.rowCount()
            self.table.insertRow(row)
            self.table.setItem(row, 0, QTableWidgetItem(str(entry.get("group"))))
            char_item = QTableWidgetItem(str(entry.get("character")))
            char_item.setToolTip(str(entry.get("path")))
            self.table.setItem(row, 1, char_item)
            raw_name = str(entry.get("name") or "")
            name_item = QTableWidgetItem(raw_name)
            name_item.setData(Qt.ItemDataRole.UserRole, entry.get("path"))
            name_item.setToolTip("%s\n%s" % (raw_name, entry.get("path") or ""))
            self.table.setItem(row, 2, name_item)
            self.table.setItem(row, 3, cn_cell(raw_name, entry.get("path") or ""))
            self.table.setItem(row, 4, QTableWidgetItem(str(entry.get("type"))))
            self.table.setItem(row, 5, QTableWidgetItem(str(entry.get("value"))))
            self.table.setItem(row, 6, QTableWidgetItem(cn_scope(entry.get("scope"))))

    # ---- 选择与修改 ----
    def _selected_paths(self):
        rows = sorted({index.row() for index in self.table.selectedIndexes()})
        paths = []
        for row in rows:
            path = _path_of(self.table, row)
            if path:
                paths.append(path)
        return paths

    def _on_double_click(self, index):
        if _note_cell(index):
            return
        paths = self._selected_paths()
        if paths:
            self._set_value(paths)

    def _set_value(self, paths=None):
        if not self.ctrl.connected:
            self.ctrl.toast("请先连接游戏")
            return
        if paths is None:
            paths = self._selected_paths()
        if not paths:
            self.ctrl.toast("请先选择要修改的行（Ctrl / Shift 可多选）")
            return
        current = ""
        row = self.table.currentRow()
        if row >= 0:
            item = self.table.item(row, 5)
            current = item.text() if item else ""
        text, ok = QInputDialog.getText(
            self, "修改属性",
            "把选中的 %d 项设为：" % len(paths), QLineEdit.EchoMode.Normal, current)
        if not ok or text.strip() == "":
            return
        self.status.setText("正在修改 %d 项…" % len(paths))
        self.ctrl.call("affection_set",
                       {"paths": paths, "value": text.strip()},
                       self._on_set_done, self._on_error)

    def _on_set_done(self, data):
        changed = data.get("changed") or 0
        failed = data.get("failed") or []
        message = "已修改 %d 项" % changed
        if failed:
            message += "，%d 项失败（%s）" % (len(failed), failed[0][1] if failed else "")
        self.status.setText(message + "。")
        self.ctrl.log("属性修改：" + message)
        self.refresh()

    def _freeze(self):
        paths = self._selected_paths()
        if not paths:
            self.ctrl.toast("请先选择要锁定的行")
            return
        for path in paths:
            self.ctrl.call("freeze", {"path": path})
        self.status.setText("已锁定 %d 项当前值，可在「数值锁定」页查看或解除。" % len(paths))

    def _cell_text(self, row, column):
        item = self.table.item(row, column)
        return item.text() if item else ""

    def _on_context_menu(self, pos):
        row = self.table.currentRow()
        path = _path_of(self.table, row) if row >= 0 else ""
        if not path:
            return
        menu = QMenu(self)
        set_action = QAction("设为…", self)
        set_action.triggered.connect(self._set_value)
        freeze_action = QAction("锁定当前值", self)
        freeze_action.triggered.connect(self._freeze)
        copy_name = QAction("复制属性名", self)
        copy_name.triggered.connect(lambda: self.ctrl.copy_text(self._cell_text(row, 2)))
        copy_cn = QAction("复制中文名", self)
        copy_cn.triggered.connect(lambda: self.ctrl.copy_text(self._cell_text(row, 3)))
        copy_action = QAction("复制变量路径", self)
        copy_action.triggered.connect(lambda: self.ctrl.copy_text(path))
        copy_value = QAction("复制当前值", self)
        copy_value.triggered.connect(lambda: self.ctrl.copy_text(self._cell_text(row, 5)))
        query_action = QAction("单个查询此属性", self)
        query_action.triggered.connect(lambda: query_path(self, path))
        menu.addAction(self.favorite_action(
            path, self._cell_text(row, 2), self._cell_text(row, 4)))
        menu.addSeparator()
        menu.addAction(set_action)
        menu.addAction(freeze_action)
        menu.addSeparator()
        menu.addAction(copy_name)
        menu.addAction(copy_cn)
        menu.addAction(copy_action)
        menu.addAction(copy_value)
        menu.addSeparator()
        menu.addAction(query_action)
        menu.exec(self.table.viewport().mapToGlobal(pos))


class SponsorPage(BasePage):
    """赞助码 / 会员奖励：自动识别赞助解锁标记并一键打开"""

    def __init__(self, ctrl):
        super().__init__(ctrl)
        self._busy = False
        self._items = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)
        self.filter_edit = QLineEdit()
        self.filter_edit.setPlaceholderText("按名称过滤，如 sponsor / gift / 礼包码")
        self.filter_edit.setFixedWidth(260)
        self.filter_edit.textChanged.connect(self._render_items)
        scan_btn = QPushButton("扫描奖励标记")
        scan_btn.clicked.connect(self.refresh)
        self.unlock_btn = QPushButton("一键解锁")
        self.unlock_btn.clicked.connect(self._unlock_all)
        self.undo_btn = QPushButton("撤销上次解锁")
        self.undo_btn.clicked.connect(self._undo)
        toolbar.addWidget(self.filter_edit)
        toolbar.addStretch(1)
        toolbar.addWidget(scan_btn)
        toolbar.addWidget(self.unlock_btn)
        toolbar.addWidget(self.undo_btn)
        layout.addLayout(toolbar)

        self.table = make_table(["变量路径", "位置", "类型", "当前值", "解锁后", "中文名"],
                                ctrl=self.ctrl)
        self.table.setColumnWidth(0, 280)
        self.table.setColumnWidth(1, 80)
        self.table.setColumnWidth(2, 80)
        self.table.setColumnWidth(3, 110)
        self.table.setColumnWidth(5, 150)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.doubleClicked.connect(self._on_double_click)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._on_context_menu)
        layout.addWidget(self.table, 1)

        self.status = QLabel(
            "点「扫描奖励标记」自动识别赞助码 / Patreon / 会员 / 礼品码（礼包码）奖励"
            "相关的变量与领取状态表。\n"
            "工具只改「开关类」变量（含已领取/未领取的条目）；"
            "若奖励写死在脚本里，请配合「画廊 · 解锁」或「物品」页使用。"
        )
        self.status.setObjectName("muted")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.bind_find(self.filter_edit, self.table)

    # ---- 生命周期 ----
    def refresh(self):
        if not self.ctrl.connected or self._busy:
            return
        self._busy = True
        self.status.setText("正在扫描赞助标记…")
        self.ctrl.call("sponsor", {}, self._on_scan, self._on_error)

    def on_connection_changed(self, connected):
        self.unlock_btn.setEnabled(connected)
        self.undo_btn.setEnabled(connected)

    def _on_error(self, message):
        self._busy = False
        self.status.setText("扫描失败：" + message)

    def _on_scan(self, data):
        self._busy = False
        self._items = data.get("items") or []
        self._render_items()
        total = data.get("total") or 0
        locked = data.get("locked") or 0
        if total == 0:
            self.status.setText(
                "没有识别到赞助相关变量。这款游戏可能把赞助奖励写死在脚本里，"
                "可先用「画廊 · 解锁」看能否打开特典 / 回忆。")
        else:
            self.status.setText(
                "识别到 %d 个赞助相关变量，其中 %d 个可直接解锁。"
                "双击可单独切换，右键可只解锁选中项。改完记得在游戏里存档。" % (total, locked))
        self.ctrl.log("赞助标记扫描：%d 项，未解锁 %d" % (total, locked))

    def _render_items(self):
        keyword = self.filter_edit.text().strip().lower()
        items = self._items
        if keyword:
            items = [item for item in items if keyword in str(item.get("path", "")).lower()]
        self.table.setRowCount(0)
        for entry in items[:1500]:
            row = self.table.rowCount()
            self.table.insertRow(row)
            raw_path = str(entry.get("path"))
            path_item = QTableWidgetItem(raw_path)
            path_item.setData(Qt.ItemDataRole.UserRole, entry.get("path"))
            note = str(entry.get("note") or "")
            path_item.setToolTip((note + "\n" if note else "") + raw_path)
            self.table.setItem(row, 0, path_item)
            self.table.setItem(row, 1, QTableWidgetItem(cn_scope(entry.get("scope"))))
            self.table.setItem(row, 2, QTableWidgetItem(str(entry.get("type"))))
            value_item = QTableWidgetItem(str(entry.get("value")))
            if entry.get("unlocked"):
                value_item.setForeground(Qt.GlobalColor.green)
            else:
                value_item.setForeground(Qt.GlobalColor.gray)
            self.table.setItem(row, 3, value_item)
            target_item = QTableWidgetItem(str(entry.get("target") or "—"))
            if not entry.get("editable"):
                target_item.setForeground(Qt.GlobalColor.darkGray)
            self.table.setItem(row, 4, target_item)
            self.table.setItem(row, 5, cn_path_cell(raw_path))

    # ---- 操作 ----
    def _locked_paths(self):
        return [entry.get("path") for entry in self._items
                if entry.get("editable") and not entry.get("unlocked") and entry.get("path")]

    def _selected_paths(self):
        rows = sorted({index.row() for index in self.table.selectedIndexes()})
        paths = []
        for row in rows:
            path = _path_of(self.table, row)
            if path:
                paths.append(path)
        return paths

    def _unlock_all(self):
        if not self.ctrl.connected:
            self.ctrl.toast("请先连接游戏")
            return
        if not self._items:
            self.ctrl.toast("请先点「扫描赞助标记」")
            return
        paths = self._selected_paths() or self._locked_paths()
        if not paths:
            self.ctrl.toast("没有可解锁的赞助标记")
            return
        answer = QMessageBox.question(
            self, "一键解锁赞助内容",
            "将打开 %d 个赞助 / 会员相关开关。\n"
            "部分游戏需要重新进入菜单才会刷新显示，建议解锁后存档重进。\n\n继续？" % len(paths))
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.status.setText("正在解锁 %d 项…" % len(paths))
        self.ctrl.call("sponsor_unlock", {"paths": paths}, self._on_unlocked, self._on_error)

    def _on_unlocked(self, data):
        changed = data.get("changed") or 0
        failed = data.get("failed") or []
        message = "已解锁 %d 项" % changed
        if failed:
            message += "，%d 项失败（%s）" % (len(failed), failed[0][1] if failed else "")
        self.status.setText(message + "。可回游戏确认；需要还原请点「撤销上次解锁」。")
        self.ctrl.log("赞助一键解锁：" + message)
        self.refresh()

    def _undo(self):
        if not self.ctrl.connected:
            return
        self.ctrl.call("sponsor_undo", {}, self._on_undo, self._on_error)

    def _on_undo(self, data):
        restored = data.get("restored") or 0
        self.status.setText("已撤销上次解锁，恢复 %d 项。" % restored)
        self.ctrl.log("撤销赞助解锁：恢复 %d 项" % restored)
        self.refresh()

    def _on_double_click(self, index):
        if _note_cell(index):
            return
        path = _path_of(self.table, index.row())
        if not path:
            return
        for entry in self._items:
            if entry.get("path") != path:
                continue
            if not entry.get("editable"):
                self.ctrl.toast(str(entry.get("note") or "该项不能直接修改"))
                return
            if entry.get("unlocked"):
                self.ctrl.toast("该项已经是解锁状态")
                return
        self._unlock_one(path)

    def _on_context_menu(self, pos):
        row = self.table.currentRow()
        path = _path_of(self.table, row) if row >= 0 else ""
        if not path:
            return
        menu = QMenu(self)
        unlock_action = QAction("解锁该项", self)
        unlock_action.triggered.connect(lambda: self._unlock_one(path))
        copy_action = QAction("复制变量路径", self)
        copy_action.triggered.connect(lambda: self.ctrl.copy_text(path))
        menu.addAction(unlock_action)
        menu.addSeparator()
        menu.addAction(copy_action)
        menu.exec(self.table.viewport().mapToGlobal(pos))

    def _unlock_one(self, path):
        self.ctrl.call("sponsor_unlock", {"paths": [path]},
                       self._on_unlocked,
                       lambda message: self.ctrl.toast("解锁失败：" + message))


class RecordsPage(BasePage):
    """CE 风格的修改记录：保存修改前后值，可随时再次修改、加备注、锁定"""

    def __init__(self, ctrl):
        super().__init__(ctrl)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        top = QHBoxLayout()
        tip = QLabel("记录按游戏保存：双击可再次修改，修改后会自动更新「修改前 / 修改后」。")
        tip.setObjectName("muted")
        self.add_btn = QPushButton("添加路径…")
        self.add_btn.clicked.connect(self._add_path)
        top.addWidget(tip, 1)
        top.addWidget(self.add_btn)
        layout.addLayout(top)

        self.table = make_table(["激活", "描述", "变量路径", "类型", "当前值", "原值", "中文名"])
        self.table.setColumnWidth(0, 48)
        self.table.setColumnWidth(1, 140)
        self.table.setColumnWidth(2, 230)
        self.table.setColumnWidth(3, 70)
        self.table.setColumnWidth(4, 120)
        self.table.setColumnWidth(5, 120)
        self.table.setColumnWidth(6, 150)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked
            | QAbstractItemView.EditTrigger.EditKeyPressed
        )
        self.table.doubleClicked.connect(self._on_double_click)
        self.table.itemChanged.connect(self._on_item_changed)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._on_context_menu)
        layout.addWidget(self.table, 1)
        self._updating = False

        bottom = QHBoxLayout()
        self.status = QLabel("")
        self.status.setObjectName("muted")
        self.edit_btn = QPushButton("修改值…")
        self.edit_btn.clicked.connect(self._edit_selected)
        self.note_btn = QPushButton("改备注…")
        self.note_btn.clicked.connect(self._edit_note)
        self.freeze_btn = QPushButton("锁定 / 解锁")
        self.freeze_btn.clicked.connect(self._toggle_freeze)
        self.live_btn = QPushButton("刷新数值")
        self.live_btn.clicked.connect(self.refresh_live)
        self.delete_btn = QPushButton("删除")
        self.delete_btn.clicked.connect(self._delete_selected)
        self.clear_btn = QPushButton("清空")
        self.clear_btn.setObjectName("danger")
        self.clear_btn.clicked.connect(self._clear)
        for btn in (self.edit_btn, self.freeze_btn, self.live_btn):
            btn.setEnabled(False)
        bottom.addWidget(self.status, 1)
        bottom.addWidget(self.edit_btn)
        bottom.addWidget(self.note_btn)
        bottom.addWidget(self.freeze_btn)
        bottom.addWidget(self.live_btn)
        bottom.addWidget(self.delete_btn)
        bottom.addWidget(self.clear_btn)
        layout.addLayout(bottom)

        self.refresh()

    # ---- 数据 ----
    def refresh(self):
        items = self.ctrl.records()
        table = self.table
        selected = self._selected_paths()
        self._updating = True
        table.setUpdatesEnabled(False)
        table.setRowCount(len(items))
        for index, item in enumerate(items):
            path = item.get("path") or ""
            frozen = bool(item.get("frozen"))

            check_item = QTableWidgetItem("")
            check_item.setFlags(
                Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
                | Qt.ItemFlag.ItemIsUserCheckable
            )
            check_item.setCheckState(
                Qt.CheckState.Checked if frozen else Qt.CheckState.Unchecked
            )
            check_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            check_item.setToolTip("勾选 = 锁定该值（相当于 CE 的激活）")

            note_item = QTableWidgetItem(item.get("note") or "")
            note_item.setToolTip("双击可直接编辑描述")

            path_item = QTableWidgetItem(path)
            path_item.setData(Qt.ItemDataRole.UserRole, path)
            path_item.setToolTip(path)
            path_item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)

            type_item = QTableWidgetItem(item.get("type") or "")
            type_item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)

            value_item = QTableWidgetItem(item.get("after") or "—")
            value_item.setData(Qt.ItemDataRole.UserRole, path)
            value_item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            value_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

            before_item = QTableWidgetItem(item.get("before") or "—")
            before_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            before_item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)

            if frozen:
                for cell in (note_item, path_item, value_item, before_item):
                    cell.setForeground(Qt.GlobalColor.yellow)
            table.setItem(index, 0, check_item)
            table.setItem(index, 1, note_item)
            table.setItem(index, 2, path_item)
            table.setItem(index, 3, type_item)
            table.setItem(index, 4, value_item)
            table.setItem(index, 5, before_item)
            table.setItem(index, 6, cn_path_cell(path))
        table.setUpdatesEnabled(True)
        self._updating = False

        for row in range(table.rowCount()):
            if _path_of(table, row) in selected:
                table.selectRow(row)
                break

        if items:
            self.status.setText(
                "共 %d 条 · 勾选「激活」= 锁定，双击描述/数值可编辑，右键更多操作" % len(items)
            )
        else:
            self.status.setText("暂无记录：在「数值搜索」里改值会自动记录，也可点右上角「添加路径…」")

    def on_connection_changed(self, connected):
        for btn in (self.edit_btn, self.freeze_btn, self.live_btn, self.add_btn):
            btn.setEnabled(connected)

    # ---- 表格交互（CE 风格）----
    def _on_item_changed(self, item):
        if self._updating:
            return
        path = _path_of(self.table, item.row())
        if not path:
            return
        if item.column() == 0:
            frozen = item.checkState() == Qt.CheckState.Checked
            self._set_frozen(path, frozen)
        elif item.column() == 1:
            self.ctrl.update_record(path, note=item.text().strip())

    def _on_double_click(self, index):
        if index.column() in (4, 5):
            self._edit_selected()
        elif index.column() == 2 and self.ctrl.connected:
            self._edit_selected()

    def refresh_live(self):
        """按记录顺序读取游戏中的当前值，刷新「当前值」列（不改动「原值」）"""
        if not self.ctrl.connected:
            self.ctrl.toast("请先连接游戏")
            return
        items = self.ctrl.records()[:100]
        if not items:
            self.ctrl.toast("暂无记录")
            return
        updated = [0]

        def one(path):
            def _ok(data):
                self._updating = True
                row = _row_of_path(self.table, path)
                if row >= 0:
                    cell = self.table.item(row, 4)
                    if cell is not None:
                        cell.setText(str(data.get("value", "")))
                self._updating = False
                updated[0] += 1
                if updated[0] == len(items):
                    self.ctrl.toast("已刷新 %d 条记录" % len(items))

            self.ctrl.call("get", {"path": path}, _ok, lambda _m: None)

        for item in items:
            one(item.get("path"))

    # ---- 选择 ----
    def _selected_paths(self):
        paths = []
        model = self.table.selectionModel()
        if model is not None:
            for index in model.selectedRows():
                path = _path_of(self.table, index.row())
                if path and path not in paths:
                    paths.append(path)
        if not paths:
            row = self.table.currentRow()
            if row >= 0:
                path = _path_of(self.table, row)
                if path:
                    paths.append(path)
        return paths

    def _single_path(self):
        paths = self._selected_paths()
        return paths[0] if paths else ""

    # ---- 操作 ----
    def _edit_selected(self):
        path = self._single_path()
        if not path:
            self.ctrl.toast("请先选择一条记录")
            return
        self.ctrl.call(
            "get",
            {"path": path},
            lambda data: self._show_editor(path, data),
            lambda message: QMessageBox.warning(self, "读取失败", message),
        )

    def _show_editor(self, path, data):
        before = str(data.get("value", ""))
        type_name = data.get("type", "")
        text, ok = QInputDialog.getText(
            self, "修改记录中的值",
            "%s（%s）\n当前值：%s\n新值：" % (path, type_name, before),
            text=before,
        )
        if not ok:
            return
        self.ctrl.call(
            "set",
            {"path": path, "value": text},
            lambda result: self._after_set(path, result, before, type_name),
            lambda message: QMessageBox.warning(self, "修改失败", message),
        )

    def _after_set(self, path, result, before, type_name):
        after = result.get("value")
        self.ctrl.record_change(path, before, after, type_name)
        self.ctrl.log("已修改 %s：%s → %s" % (path, before, after))
        self.ctrl.toast("已修改 %s" % path)

    def _edit_note(self):
        path = self._single_path()
        if not path:
            self.ctrl.toast("请先选择一条记录")
            return
        current = ""
        for item in self.ctrl.records():
            if item.get("path") == path:
                current = item.get("note") or ""
                break
        note, ok = QInputDialog.getText(self, "修改备注", "%s 的备注：" % path, text=current)
        if ok:
            self.ctrl.update_record(path, note=note.strip())

    def _record_of(self, path):
        for item in self.ctrl.records():
            if item.get("path") == path:
                return item
        return None

    def _toggle_freeze(self):
        path = self._single_path()
        if not path:
            self.ctrl.toast("请先选择一条记录")
            return
        record = self._record_of(path)
        self._set_frozen(path, not bool(record and record.get("frozen")), record)

    def _set_frozen(self, path, frozen, record=None):
        if frozen:
            if not self.ctrl.connected:
                self.ctrl.toast("请先连接游戏再锁定")
                self.refresh()
                return
            payload = {"path": path}
            after = (record or {}).get("after") or ""
            if after and after != "—":
                payload["value"] = after
            self.ctrl.call(
                "freeze",
                payload,
                lambda data: self._after_freeze(path, True, data),
                lambda message: QMessageBox.warning(self, "锁定失败", message),
            )
        else:
            if not self.ctrl.connected:
                self.ctrl.toast("请先连接游戏再解除锁定")
                self.refresh()
                return
            self.ctrl.call(
                "unfreeze",
                {"path": path},
                lambda _data: self._after_freeze(path, False),
                lambda message: QMessageBox.warning(self, "解除锁定失败", message),
            )

    def _after_freeze(self, path, frozen, data=None):
        changes = {"frozen": frozen}
        if data is not None:
            changes["after"] = data.get("value", "")
        self.ctrl.update_record(path, **changes)
        text = "已锁定 %s" % path if frozen else "已解除锁定 %s" % path
        self.ctrl.log(text)
        self.ctrl.toast(text)

    def _delete_selected(self):
        paths = self._selected_paths()
        if not paths:
            self.ctrl.toast("请先选择记录")
            return
        confirm = QMessageBox.question(
            self, "删除记录",
            "确定删除选中的 %d 条记录吗？\n（仅删除工具的记录，不修改游戏数据）" % len(paths),
        )
        if confirm == QMessageBox.StandardButton.Yes:
            self.ctrl.remove_records(paths)

    def _clear(self):
        if not self.ctrl.records():
            self.ctrl.toast("暂无记录")
            return
        confirm = QMessageBox.question(
            self, "清空记录", "确定清空本游戏的全部修改记录吗？\n（仅删除工具的记录，不修改游戏数据）"
        )
        if confirm == QMessageBox.StandardButton.Yes:
            self.ctrl.clear_records()

    def _add_path(self):
        if not self.ctrl.connected:
            self.ctrl.toast("请先连接游戏")
            return
        path, ok = QInputDialog.getText(
            self, "添加记录",
            "要记录的变量路径（例如 g_gold、player.gold、persistent.money）：",
        )
        path = path.strip() if ok else ""
        if not path:
            return
        self.ctrl.call(
            "get",
            {"path": path},
            lambda data: self._add_path_ok(path, data),
            lambda message: QMessageBox.warning(self, "添加失败", message),
        )

    def _add_path_ok(self, path, data):
        if self.ctrl.has_record(path):
            self.ctrl.toast("该路径已在记录中")
            return
        self.ctrl.record_change(path, data.get("value"), "—", data.get("type", ""))
        self.ctrl.toast("已加入记录：" + path)

    def _on_context_menu(self, pos):
        index = self.table.indexAt(pos)
        if not index.isValid():
            return
        menu = QMenu(self)
        edit_action = QAction("修改值…", self)
        edit_action.triggered.connect(self._edit_selected)
        note_action = QAction("改备注…", self)
        note_action.triggered.connect(self._edit_note)
        freeze_action = QAction("锁定 / 解锁", self)
        freeze_action.triggered.connect(self._toggle_freeze)
        copy_action = QAction("复制路径", self)
        copy_action.triggered.connect(lambda: self.ctrl.copy_text(_path_of(self.table, index.row())))
        delete_action = QAction("删除记录", self)
        delete_action.triggered.connect(self._delete_selected)
        menu.addAction(edit_action)
        menu.addAction(note_action)
        menu.addAction(freeze_action)
        menu.addSeparator()
        menu.addAction(copy_action)
        menu.addAction(delete_action)
        menu.exec(self.table.viewport().mapToGlobal(pos))


class LogPage(BasePage):
    def __init__(self, ctrl):
        super().__init__(ctrl)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        top = QHBoxLayout()
        tip = QLabel("工具与游戏端的操作记录")
        tip.setObjectName("muted")
        fetch_btn = QPushButton("获取游戏端日志")
        fetch_btn.clicked.connect(self._fetch)
        clear_btn = QPushButton("清空")
        clear_btn.clicked.connect(lambda: self.text.clear())
        top.addWidget(tip, 1)
        top.addWidget(fetch_btn)
        top.addWidget(clear_btn)
        layout.addLayout(top)

        self.text = QPlainTextEdit()
        self.text.setReadOnly(True)
        self.text.setMaximumBlockCount(3000)
        layout.addWidget(self.text, 1)

    def _fetch(self):
        if not self.ctrl.connected:
            self.ctrl.toast("请先连接游戏")
            return
        self.ctrl.call(
            "logs",
            {},
            lambda data: self._append_lines(data.get("items") or []),
            lambda message: self.ctrl.toast(message),
        )

    def _append_lines(self, lines):
        for line in lines:
            self.text.appendPlainText("[游戏] " + str(line))
