# -*- coding: utf-8 -*-
from datetime import datetime

from playwright.async_api import Playwright, async_playwright, Page, Browser
import os
import asyncio

from src.config import settings
from src.utils.base_social_media import set_init_script
from src.utils.log import douyin_logger


async def cookie_auth(account_file):
    from playwright._impl._errors import TimeoutError as PlaywrightTimeoutError
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=settings.uploader_headless)
        try:
            context = await browser.new_context(storage_state=account_file)
            context = await set_init_script(context)
            page = await context.new_page()
            try:
                # 增加页面加载超时时间为30秒，适配 Docker 或慢网环境
                await page.goto("https://creator.douyin.com/creator-micro/content/upload", timeout=30000)
            except PlaywrightTimeoutError:
                douyin_logger.warning("[+] 访问抖音创作者中心超时，网络可能不可用")
                return False
            except Exception as e:
                douyin_logger.warning(f"[+] 访问抖音创作者中心失败: {e}")
                return False
            
            try:
                # 等待页面重定向或完成加载
                await page.wait_for_load_state("networkidle", timeout=10000)
            except:
                pass

            # 检查是否仍在登录页（出现以下任意元素即表示未成功自动登录）
            is_at_login = await page.evaluate("""
                () => {
                    const text = document.body.innerText;
                    return text.includes('手机号登录') || text.includes('扫码登录') || text.includes('密码登录')
                        || !!document.querySelector('.login-mask') || !!document.querySelector('.login-container');
                }
            """)

            if is_at_login:
                douyin_logger.info("[+] Cookie 已失效，处于登录页")
                return False
            else:
                douyin_logger.info("[+] Cookie 有效")
                return True
        finally:
            try:
                if "context" in locals() and context:
                    await context.close()
            except:
                pass
            try:
                if "browser" in locals() and browser:
                    await browser.close()
            except:
                pass


async def douyin_setup(account_file, handle=False):
    if not os.path.exists(account_file) or not await cookie_auth(account_file):
        if not handle:
            return False
        douyin_logger.info('[+] cookie文件不存在或已失效,即将自动打开浏览器,请扫码登录,登陆后会自动生成cookie文件')
        await douyin_cookie_gen(account_file)
    return True


async def douyin_cookie_gen(account_file):
    async with async_playwright() as playwright:
        options = {'headless': settings.uploader_headless}
        browser = await playwright.chromium.launch(**options)
        context = await browser.new_context()
        try:
            context = await set_init_script(context)
            page = await context.new_page()
            await page.goto("https://creator.douyin.com/")
            await page.pause()
            await context.storage_state(path=account_file)
        finally:
            if context:
                await context.close()
            if browser:
                await browser.close()


class DouYinVideo(object):
    def __init__(self, title, file_path, tags, publish_date: datetime, account_file, thumbnail_path=None, productLink='', productTitle=''):
        self.title = title
        self.file_path = file_path
        self.tags = tags
        self.publish_date = publish_date
        self.account_file = account_file
        self.date_format = '%Y年%m月%d日 %H:%M'
        self.local_executable_path = settings.uploader_chrome_path
        self.headless = settings.uploader_headless
        self.thumbnail_path = thumbnail_path
        self.productLink = productLink
        self.productTitle = productTitle

    async def set_schedule_time_douyin(self, page, publish_date):
        label_element = page.locator("[class^='radio']:has-text('定时发布')")
        await label_element.click()
        await asyncio.sleep(1)
        publish_date_hour = publish_date.strftime("%Y-%m-%d %H:%M")
        await asyncio.sleep(1)
        await page.locator('.semi-input[placeholder="日期和时间"]').click()
        await page.keyboard.press("Control+KeyA")
        await page.keyboard.type(str(publish_date_hour))
        await page.keyboard.press("Enter")
        await asyncio.sleep(1)

    async def handle_upload_error(self, page):
        douyin_logger.info('视频出错了，重新上传中')
        await page.locator('div.progress-div [class^="upload-btn-input"]').set_input_files(self.file_path)

    async def upload(self, playwright: Playwright = None, browser: Browser = None) -> None:
        close_browser_when_done = False
        if browser is None:
            if not playwright:
                raise ValueError("You must provide either 'playwright' or 'browser'")
            close_browser_when_done = True
            if self.local_executable_path:
                browser = await playwright.chromium.launch(headless=self.headless, executable_path=self.local_executable_path)
            else:
                browser = await playwright.chromium.launch(headless=self.headless)
        context = await browser.new_context(storage_state=f"{self.account_file}")
        try:
            context = await set_init_script(context)
            page = await context.new_page()
            await page.goto("https://creator.douyin.com/creator-micro/content/upload")
            douyin_logger.info(f'[+]正在上传-------{self.title}.mp4')
            douyin_logger.info(f'[-] 正在打开主页...')
            await page.wait_for_url("https://creator.douyin.com/creator-micro/content/upload")
            await page.locator("div[class^='container'] input").set_input_files(self.file_path)

            while True:
                try:
                    await page.wait_for_url(
                        "https://creator.douyin.com/creator-micro/content/publish?enter_from=publish_page", timeout=3000)
                    douyin_logger.info("[+] 成功进入version_1发布页面!")
                    break
                except Exception:
                    try:
                        await page.wait_for_url(
                            "https://creator.douyin.com/creator-micro/content/post/video?enter_from=publish_page",
                            timeout=3000)
                        douyin_logger.info("[+] 成功进入version_2发布页面!")
                        break
                    except:
                        print("  [-] 超时未进入视频发布页面，重新尝试...")
                        await asyncio.sleep(0.5)

            await asyncio.sleep(1)
            douyin_logger.info(f'  [-] 正在填充标题和话题...')
            title_container = page.get_by_text('作品标题').locator("..").locator("xpath=following-sibling::div[1]").locator("input")
            if await title_container.count():
                await title_container.fill(self.title[:30])
            else:
                titlecontainer = page.locator(".notranslate")
                await titlecontainer.click()
                await page.keyboard.press("Backspace")
                await page.keyboard.press("Control+KeyA")
                await page.keyboard.press("Delete")
                await page.keyboard.type(self.title)
                await page.keyboard.press("Enter")
            css_selector = ".zone-container"
            for index, tag in enumerate(self.tags, start=1):
                await page.type(css_selector, "#" + tag)
                await page.press(css_selector, "Space")
            douyin_logger.info(f'总共添加{len(self.tags)}个话题')
            while True:
                try:
                    number = await page.locator('[class^="long-card"] div:has-text("重新上传")').count()
                    if number > 0:
                        douyin_logger.success("  [-]视频上传完毕")
                        break
                    else:
                        douyin_logger.info("  [-] 正在上传视频中...")
                        await asyncio.sleep(2)
                        if await page.locator('div.progress-div > div:has-text("上传失败")').count():
                            douyin_logger.error("  [-] 发现上传出错了... 准备重试")
                            await self.handle_upload_error(page)
                except:
                    douyin_logger.info("  [-] 正在上传视频中...")
                    await asyncio.sleep(2)

            if self.productLink and self.productTitle:
                douyin_logger.info(f'  [-] 正在设置商品链接...')
                await self.set_product_link(page, self.productLink, self.productTitle)
                douyin_logger.info(f'  [+] 完成设置商品链接...')

            await self.set_thumbnail(page, self.thumbnail_path)
            await self.set_location(page, "")

            third_part_element = '[class^="info"] > [class^="first-part"] div div.semi-switch'
            if await page.locator(third_part_element).count():
                if 'semi-switch-checked' not in await page.eval_on_selector(third_part_element, 'div => div.className'):
                    await page.locator(third_part_element).locator('input.semi-switch-native-control').click()

            if self.publish_date != 0:
                await self.set_schedule_time_douyin(page, self.publish_date)

            while True:
                try:
                    publish_button = page.get_by_role('button', name="发布", exact=True)
                    if await publish_button.count():
                        await publish_button.click()
                    await page.wait_for_url("https://creator.douyin.com/creator-micro/content/manage**", timeout=3000)
                    douyin_logger.success("  [-]视频发布成功")
                    break
                except:
                    await self.handle_auto_video_cover(page)
                    douyin_logger.info("  [-] 视频正在发布中...")
                    await page.screenshot(full_page=True)
                    await asyncio.sleep(0.5)

            await context.storage_state(path=self.account_file)
            douyin_logger.success('  [-]cookie更新完毕！')
            await asyncio.sleep(2)
        finally:
            if context:
                await context.close()
            if close_browser_when_done and browser:
                await browser.close()

    async def handle_auto_video_cover(self, page):
        if await page.get_by_text("请设置封面后再发布").first.is_visible():
            print("  [-] 检测到需要设置封面提示...")
            recommend_cover = page.locator('[class^="recommendCover-"]').first
            if await recommend_cover.count():
                print("  [-] 正在选择第一个推荐封面...")
                try:
                    await recommend_cover.click()
                    await asyncio.sleep(1)
                    confirm_text = "是否确认应用此封面？"
                    if await page.get_by_text(confirm_text).first.is_visible():
                        await page.get_by_role("button", name="确定").click()
                        await asyncio.sleep(1)
                    return True
                except Exception as e:
                    print(f"  [-] 选择封面失败: {e}")
        return False

    async def set_thumbnail(self, page: Page, thumbnail_path: str):
        if thumbnail_path:
            douyin_logger.info('  [-] 正在设置视频封面...')
            await page.click('text="选择封面"')
            await page.wait_for_selector("div.dy-creator-content-modal")
            await page.click('text="设置竖封面"')
            await page.wait_for_timeout(2000)
            await page.locator("div[class^='semi-upload upload'] >> input.semi-upload-hidden-input").set_input_files(thumbnail_path)
            await page.wait_for_timeout(2000)
            await page.locator("div#tooltip-container button:visible:has-text('完成')").click()
            douyin_logger.info('  [+] 视频封面设置完成！')
            await page.wait_for_selector("div.extractFooter", state='detached')

    async def set_location(self, page: Page, location: str = ""):
        if not location:
            return

    async def handle_product_dialog(self, page: Page, product_title: str):
        await page.wait_for_timeout(2000)
        await page.wait_for_selector('input[placeholder="请输入商品短标题"]', timeout=10000)
        short_title_input = page.locator('input[placeholder="请输入商品短标题"]')
        if not await short_title_input.count():
            douyin_logger.error("[-] 未找到商品短标题输入框")
            return False
        product_title = product_title[:10]
        await short_title_input.fill(product_title)
        await page.wait_for_timeout(1000)
        finish_button = page.locator('button:has-text("完成编辑")')
        if 'disabled' not in await finish_button.get_attribute('class'):
            await finish_button.click()
            await page.wait_for_selector('.semi-modal-content', state='hidden', timeout=5000)
            return True
        else:
            cancel_button = page.locator('button:has-text("取消")')
            if await cancel_button.count():
                await cancel_button.click()
            else:
                await page.locator('.semi-modal-close').click()
            await page.wait_for_selector('.semi-modal-content', state='hidden', timeout=5000)
            return False

    async def set_product_link(self, page: Page, product_link: str, product_title: str):
        await page.wait_for_timeout(2000)
        try:
            await page.wait_for_selector('text=添加标签', timeout=10000)
            dropdown = page.get_by_text('添加标签').locator("..").locator("..").locator("..").locator(".semi-select").first
            if not await dropdown.count():
                douyin_logger.error("[-] 未找到标签下拉框")
                return False
            await dropdown.click()
            await page.wait_for_selector('[role="listbox"]', timeout=5000)
            await page.locator('[role="option"]:has-text("购物车")').click()
            await page.wait_for_selector('input[placeholder="粘贴商品链接"]', timeout=5000)
            input_field = page.locator('input[placeholder="粘贴商品链接"]')
            await input_field.fill(product_link)
            add_button = page.locator('span:has-text("添加链接")')
            button_class = await add_button.get_attribute('class')
            if button_class and 'disable' in button_class:
                douyin_logger.error("[-] '添加链接'按钮不可用")
                return False
            await add_button.click()
            await page.wait_for_timeout(2000)
            error_modal = page.locator('text=未搜索到对应商品')
            if await error_modal.count():
                await page.locator('button:has-text("确定")').click()
                douyin_logger.error("[-] 商品链接无效")
                return False
            if not await self.handle_product_dialog(page, product_title):
                return False
            return True
        except Exception as e:
            douyin_logger.error(f"[-] 设置商品链接时出错: {str(e)}")
            return False

    async def main(self, browser: Browser = None):
        if browser:
            await self.upload(browser=browser)
        else:
            async with async_playwright() as playwright:
                await self.upload(playwright=playwright)
