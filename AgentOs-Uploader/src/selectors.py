# -*- coding: utf-8 -*-
"""
平台 UI 选择器集中配置
将硬编码的 CSS/XPath 选择器抽取到此处，应对平台改版只需在此更新。
"""

# ────────────────────────────────────────────────────────────────────────────
# 小红书 (XiaoHongShu)
# ────────────────────────────────────────────────────────────────────────────
XHS_SELECTORS: dict = {
    # 上传页面 – 视频文件选择 input
    "upload_input": "div[class^='upload-content'] input[class='upload-input']",
    # 上传成功状态标识（wait_for_function 中直接用 JS 字符串匹配）
    "upload_success_text": "上传成功",

    # 作品标题输入框（两种 DOM 结构兼容）
    "title_input": "div.plugin.title-container input.d-text",
    "title_input_fallback": ".notranslate",

    # 描述 / 话题编辑器
    "desc_editor": ".ql-editor",

    # 定时发布
    "schedule_label": "label:has-text('定时发布')",
    "schedule_datetime_input": ".el-input__inner[placeholder='选择日期和时间']",

    # 私密发布
    "private_label": "label:has-text('私密')",
    "private_text": "仅自己可见",

    # 发布 / 定时发布 按钮（使用 str.format 时注入 btn_text）
    "publish_button": "button:has-text('{btn_text}')",

    # 封面设置
    "thumbnail_select_btn": "text='选择封面'",
    "thumbnail_modal": "div.semi-modal-content",
    "thumbnail_vertical_btn": "text='设置竖封面'",
    "thumbnail_upload_input": "div[class^='semi-upload upload'] >> input.semi-upload-hidden-input",
    "thumbnail_finish_button": "div[class^='extractFooter'] button:visible:has-text('完成')",

    # Cookie 校验页
    "cookie_check_url": "https://creator.xiaohongshu.com/creator-micro/content/upload",
    "login_text_phone": "手机号登录",
    "login_text_qr": "扫码登录",
}

# ────────────────────────────────────────────────────────────────────────────
# 抖音 (DouYin)
# ────────────────────────────────────────────────────────────────────────────
DOUYIN_SELECTORS: dict = {
    # 上传
    "upload_input": "label.upload-btn-input input[type='file']",
    "upload_success": "div.progress-div >> div:has-text('上传完成')",

    # 标题 / 描述
    "title_input": ".notranslate",
    "desc_editor": ".ql-editor",

    # 发布按钮
    "publish_button": "button:has-text('发布')",
    "schedule_publish_button": "button:has-text('定时发布')",

    # 定时发布
    "schedule_label": "label:has-text('定时发布')",
    "schedule_datetime_input": ".schedule-date-picker input",

    # 成功 URL 片段
    "login_success_url_patterns": [
        "creator-micro/content/upload",
        "creator.douyin.com/creator-micro",
        "creator.douyin.com/home",
        "creator.douyin.com/dashboard",
    ],

    # Cookie 校验
    "cookie_check_url": "https://creator.douyin.com/creator-micro/content/upload",
}

# ────────────────────────────────────────────────────────────────────────────
# 视频号 (Tencent Channels)
# ────────────────────────────────────────────────────────────────────────────
TENCENT_SELECTORS: dict = {
    # 上传
    "upload_input": "input[type='file']",

    # 标题 / 描述
    "title_input": "input[placeholder*='标题']",
    "desc_editor": "textarea[placeholder*='简介']",

    # 发布按钮
    "publish_button": "button:has-text('发表')",

    # 成功 URL 片段
    "login_success_url_patterns": [
        "platform/post/create",
        "platform/post/list",
        "#/platform",
        "#/creator",
        "channels.weixin.qq.com/platform",
    ],

    # Cookie 校验
    "cookie_check_url": "https://channels.weixin.qq.com/platform/post/list",
}
