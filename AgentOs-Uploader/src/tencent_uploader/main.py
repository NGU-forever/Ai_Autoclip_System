# -*- coding: utf-8 -*-
from datetime import datetime
from pathlib import Path

from playwright.async_api import Playwright, async_playwright
import os
import asyncio

from uploader.conf import LOCAL_CHROME_PATH, LOCAL_CHROME_HEADLESS, COOKIES_DIR
from uploader.utils.base_social_media import set_init_script
from uploader.utils.log import tencent_logger


def format_str_for_short_title(origin_title: str) -> str:
    allowed_special_chars = "《》“”:+?%°"
    filtered_chars = [char if char.isalnum() or char in allowed_special_chars else ' ' if char == ',' else '' for char in origin_title]
    formatted_string = ''.join(filtered_chars)
    if len(formatted_string) > 16:
        formatted_string = formatted_string[:16]
    elif len(formatted_string) < 6:
        formatted_string += ' ' * (6 - len(formatted_string))
    return formatted_string


def _resolve_account_file(account_file) -> str:
    """解析 account_file：若为相对路径则解析到 cookies 目录"""
    p = Path(account_file)
    if p.is_absolute():
        return str(p)
    return str(COOKIES_DIR / account_file)


async def cookie_auth(account_file):
    from playwright._impl._errors import TimeoutError as PlaywrightTimeoutError
    resolved = _resolve_account_file(account_file)
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=LOCAL_CHROME_HEADLESS)
        try:
            context = await browser.new_context(storage_state=resolved)
            context = await set_init_script(context)
            page = await context.new_page()
            try:
                # 缩短页面加载超时时间为10秒
                await page.goto("https://channels.weixin.qq.com/platform/post/create", timeout=10000)
            except PlaywrightTimeoutError:
                tencent_logger.warning("[+] 访问视频号平台超时，网络可能不可用")
                return False
            except Exception as e:
                tencent_logger.warning(f"[+] 访问视频号平台失败: {e}")
                return False
            try:
                await page.wait_for_selector('div.title-name:has-text("微信小店")', timeout=5000)
                tencent_logger.error("[+] 等待5秒 cookie 失效")
                return False
            except:
                tencent_logger.success("[+] cookie 有效")
                return True
        finally:
            await context.close()
            await browser.close()


async def get_tencent_cookie(account_file):
    async with async_playwright() as playwright:
        options = {'args': ['--lang en-GB'], 'headless': LOCAL_CHROME_HEADLESS}
        browser = await playwright.chromium.launch(**options)
        context = await browser.new_context()
        context = await set_init_script(context)
        page = await context.new_page()
        await page.goto("https://channels.weixin.qq.com")
        await page.pause()
        await context.storage_state(path=account_file)


async def weixin_setup(account_file, handle=False):
    resolved = _resolve_account_file(account_file)
    if not os.path.exists(resolved) or not await cookie_auth(account_file):
        if not handle:
            return False
        tencent_logger.info('[+] cookie文件不存在或已失效,即将自动打开浏览器,请扫码登录,登陆后会自动生成cookie文件')
        await get_tencent_cookie(resolved)
    return True


class TencentVideo(object):
    def __init__(self, title, file_path, tags, publish_date: datetime, account_file, category=None, is_draft=False, short_title=None, declare_original=False):
        self.title = title
        self.file_path = file_path
        self.tags = tags
        self.publish_date = publish_date
        self.account_file = _resolve_account_file(account_file)
        self.category = category
        self.headless = LOCAL_CHROME_HEADLESS
        self.is_draft = is_draft
        self.local_executable_path = LOCAL_CHROME_PATH or None
        self.short_title = short_title
        self.declare_original = declare_original

    async def set_schedule_time_tencent(self, page, publish_date):
        label_element = page.locator("label").filter(has_text="定时").nth(1)
        await label_element.click()
        await page.click('input[placeholder="请选择发表时间"]')
        str_month = str(publish_date.month) if publish_date.month > 9 else "0" + str(publish_date.month)
        current_month = str_month + "月"
        page_month = await page.inner_text('span.weui-desktop-picker__panel__label:has-text("月")')
        if page_month != current_month:
            await page.click('button.weui-desktop-btn__icon__right')
        elements = await page.query_selector_all('table.weui-desktop-picker__table a')
        for element in elements:
            if 'weui-desktop-picker__disabled' in await element.evaluate('el => el.className'):
                continue
            text = await element.inner_text()
            if text.strip() == str(publish_date.day):
                await element.click()
                break
        await page.click('input[placeholder="请选择时间"]')
        await page.keyboard.press("Control+KeyA")
        await page.keyboard.type(str(publish_date.hour))
        await page.locator("div.input-editor").click()

    async def handle_upload_error(self, page):
        tencent_logger.info("视频出错了，重新上传中")
        await page.locator('div.media-status-content div.tag-inner:has-text("删除")').click()
        await page.get_by_role('button', name="删除", exact=True).click()
        file_input = page.locator('input[type="file"]')
        await file_input.set_input_files(self.file_path)

    async def upload(self, playwright: Playwright) -> None:
        browser = await playwright.chromium.launch(headless=self.headless, executable_path=self.local_executable_path)
        context = await browser.new_context(storage_state=f"{self.account_file}")
        context = await set_init_script(context)
        page = await context.new_page()
        await page.goto("https://channels.weixin.qq.com/platform/post/create")
        tencent_logger.info(f'[+]正在上传-------{self.title}.mp4')
        await page.wait_for_url("https://channels.weixin.qq.com/platform/post/create")
        file_input = page.locator('input[type="file"]')
        await file_input.set_input_files(self.file_path)
        await self.add_title_tags(page)
        await self.add_collection(page)
        await self.add_original(page)
        await self.detect_upload_status(page)
        if self.publish_date != 0:
            await self.set_schedule_time_tencent(page, self.publish_date)
        await self.add_short_title(page)
        await self.click_publish(page)
        await context.storage_state(path=f"{self.account_file}")
        tencent_logger.success('  [-]cookie更新完毕!')
        await asyncio.sleep(2)
        await context.close()
        await browser.close()

    async def add_short_title(self, page):
        short_title_element = page.get_by_text("短标题", exact=True).locator("..").locator(
            "xpath=following-sibling::div").locator('span input[type="text"]')
        if await short_title_element.count():
            # 使用自定义短标题或根据标题自动生成
            short_title = self.short_title if self.short_title else format_str_for_short_title(self.title)
            # 确保长度在6-16字符之间
            if len(short_title) < 6:
                short_title = short_title + " " * (6 - len(short_title))
            if len(short_title) > 16:
                short_title = short_title[:16]
            await short_title_element.fill(short_title)

    async def click_publish(self, page):
        while True:
            try:
                if self.is_draft:
                    draft_button = page.locator('div.form-btns button:has-text("保存草稿")')
                    if await draft_button.count():
                        await draft_button.click()
                    await page.wait_for_url("**/post/list**", timeout=5000)
                    tencent_logger.success("  [-]视频草稿保存成功")
                else:
                    publish_button = page.locator('div.form-btns button:has-text("发表")')
                    if await publish_button.count():
                        await publish_button.click()
                    await page.wait_for_url("https://channels.weixin.qq.com/platform/post/list", timeout=5000)
                    tencent_logger.success("  [-]视频发布成功")
                break
            except Exception as e:
                current_url = page.url
                if self.is_draft:
                    if "post/list" in current_url or "draft" in current_url:
                        tencent_logger.success("  [-]视频草稿保存成功")
                        break
                else:
                    if "https://channels.weixin.qq.com/platform/post/list" in current_url:
                        tencent_logger.success("  [-]视频发布成功")
                        break
                tencent_logger.exception(f"  [-] Exception: {e}")
                tencent_logger.info("  [-] 视频正在发布中...")
                await asyncio.sleep(0.5)

    async def detect_upload_status(self, page):
        while True:
            try:
                if "weui-desktop-btn_disabled" not in await page.get_by_role("button", name="发表").get_attribute('class'):
                    tencent_logger.info("  [-]视频上传完毕")
                    break
                else:
                    tencent_logger.info("  [-] 正在上传视频中...")
                    await asyncio.sleep(2)
                    if await page.locator('div.status-msg.error').count() and await page.locator(
                            'div.media-status-content div.tag-inner:has-text("删除")').count():
                        tencent_logger.error("  [-] 发现上传出错了...准备重试")
                        await self.handle_upload_error(page)
            except:
                tencent_logger.info("  [-] 正在上传视频中...")
                await asyncio.sleep(2)

    async def add_title_tags(self, page):
        await page.locator("div.input-editor").click()
        await page.keyboard.type(self.title)
        await page.keyboard.press("Enter")
        for index, tag in enumerate(self.tags, start=1):
            await page.keyboard.type("#" + tag)
            await page.keyboard.press("Space")
        tencent_logger.info(f"成功添加hashtag: {len(self.tags)}")

    async def add_collection(self, page):
        collection_elements = page.get_by_text("添加到合集").locator("xpath=following-sibling::div").locator(
            '.option-list-wrap > div')
        if await collection_elements.count() > 1:
            await page.get_by_text("添加到合集").locator("xpath=following-sibling::div").click()
            await collection_elements.first.click()

    async def add_original(self, page):
        # 只有用户勾选原创声明时才执行
        if not self.declare_original:
            return
            
        if await page.get_by_label("视频为原创").count():
            await page.get_by_label("视频为原创").check()
        label_locator = await page.locator('label:has-text("我已阅读并同意 《视频号原创声明使用条款》")').is_visible()
        if label_locator:
            await page.get_by_label("我已阅读并同意 《视频号原创声明使用条款》").check()
            await page.get_by_role("button", name="声明原创").click()
        if await page.locator('div.label span:has-text("声明原创")').count() and self.category:
            if not await page.locator('div.declare-original-checkbox input.ant-checkbox-input').is_disabled():
                await page.locator('div.declare-original-checkbox input.ant-checkbox-input').click()
                if not await page.locator(
                        'div.declare-original-dialog label.ant-checkbox-wrapper.ant-checkbox-wrapper-checked:visible').count():
                    await page.locator('div.declare-original-dialog input.ant-checkbox-input:visible').click()
            if await page.locator('div.original-type-form > div.form-label:has-text("原创类型"):visible').count():
                await page.locator('div.form-content:visible').click()
                await page.locator(
                    f'div.form-content:visible ul.weui-desktop-dropdown__list li.weui-desktop-dropdown__list-ele:has-text("{self.category}")').first.click()
                await page.wait_for_timeout(1000)
            if await page.locator('button:has-text("声明原创"):visible').count():
                await page.locator('button:has-text("声明原创"):visible').click()

    async def main(self):
        async with async_playwright() as playwright:
            await self.upload(playwright)
