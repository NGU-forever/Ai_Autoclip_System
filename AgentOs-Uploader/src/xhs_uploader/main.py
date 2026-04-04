# -*- coding: utf-8 -*-
from datetime import datetime

from playwright.async_api import Playwright, async_playwright, Page, Browser, TimeoutError as PlaywrightTimeoutError
import os
import asyncio

from src.config import settings
from src.utils.base_social_media import set_init_script
from src.utils.log import xiaohongshu_logger
from src.platform_selectors import XHS_SELECTORS


async def cookie_auth(account_file):
    from playwright._impl._errors import TimeoutError as PlaywrightTimeoutError
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=settings.uploader_headless)
        try:
            context = await browser.new_context(storage_state=account_file)
            context = await set_init_script(context)
            # 创建一个新的页面
            page = await context.new_page()
            # 访问指定的 URL
            try:
                # 缩短页面加载超时时间为10秒
                await page.goto("https://creator.xiaohongshu.com/creator-micro/content/upload", timeout=10000)
            except PlaywrightTimeoutError:
                xiaohongshu_logger.warning("[+] 访问小红书创作者中心超时，网络可能不可用")
                return False
            except Exception as e:
                xiaohongshu_logger.warning(f"[+] 访问小红书创作者中心失败: {e}")
                return False
            try:
                await page.wait_for_url("https://creator.xiaohongshu.com/creator-micro/content/upload", timeout=5000)
            except:
                print("[+] 等待5秒 cookie 失效")
                return False
            if await page.get_by_text('手机号登录').count() or await page.get_by_text('扫码登录').count():
                print("[+] 等待5秒 cookie 失效")
                return False
            else:
                print("[+] cookie 有效")
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


async def xiaohongshu_setup(account_file, handle=False):
    if not os.path.exists(account_file) or not await cookie_auth(account_file):
        if not handle:
            # Todo alert message
            return False
        xiaohongshu_logger.info('[+] cookie文件不存在或已失效，即将自动打开浏览器，请扫码登录，登陆后会自动生成cookie文件')
        await xiaohongshu_cookie_gen(account_file)
    return True


async def xiaohongshu_cookie_gen(account_file):
    async with async_playwright() as playwright:
        options = {
            'headless': settings.uploader_headless
        }
        # Make sure to run headed.
        browser = await playwright.chromium.launch(**options)
        # Setup context however you like.
        context = await browser.new_context()  # Pass any options
        try:
            context = await set_init_script(context)
            # Pause the page, and start recording manually.
            page = await context.new_page()
            await page.goto("https://creator.xiaohongshu.com/")
            await page.pause()
            # 点击调试器的继续，保存cookie
            await context.storage_state(path=account_file)
        finally:
            if context:
                await context.close()
            if browser:
                await browser.close()


class XiaoHongShuVideo(object):
    def __init__(
        self,
        title,
        file_path,
        tags,
        publish_date: datetime,
        account_file,
        thumbnail_path=None,
        desc=None,
        is_private=False,
    ):
        self.title = title  # 视频标题
        self.file_path = file_path
        self.tags = tags
        self.publish_date = publish_date
        self.account_file = account_file
        self.date_format = '%Y年%m月%d日 %H:%M'
        self.local_executable_path = settings.uploader_chrome_path
        self.headless = settings.uploader_headless
        self.thumbnail_path = thumbnail_path
        self.desc = (desc or "").strip() if desc else ""
        self.is_private = is_private

    async def set_schedule_time_xiaohongshu(self, page, publish_date):
        xiaohongshu_logger.info("  [-] 正在设置定时发布时间...")
        xiaohongshu_logger.info(f"publish_date: {publish_date}")

        label_element = page.locator("label:has-text('定时发布')")
        await label_element.wait_for(state="visible", timeout=8000)
        await label_element.click()

        publish_date_hour = publish_date.strftime("%Y-%m-%d %H:%M")
        xiaohongshu_logger.info(f"publish_date_hour: {publish_date_hour}")

        # 等待时间选择器出现后再交互
        date_input = page.locator('.el-input__inner[placeholder="选择日期和时间"]')
        await date_input.wait_for(state="visible", timeout=6000)
        await date_input.click()
        await page.keyboard.press("Control+KeyA")
        await page.keyboard.type(str(publish_date_hour))
        await page.keyboard.press("Enter")

        # 等待输入框值更新而不是盲目 sleep
        await page.wait_for_function(
            f"() => document.querySelector('.el-input__inner[placeholder=\"选择日期和时间\"]')?.value?.includes('{publish_date_hour[:7]}')",
            timeout=5000,
        )

    async def handle_upload_error(self, page):
        xiaohongshu_logger.info('视频出错了，重新上传中')
        await page.locator('div.progress-div [class^="upload-btn-input"]').set_input_files(self.file_path)

    async def upload(self, playwright: Playwright = None, browser: Browser = None) -> None:
        close_browser_when_done = False
        if browser is None:
            if not playwright:
                raise ValueError("You must provide either 'playwright' or 'browser'")
            close_browser_when_done = True
            # 使用 Chromium 浏览器启动一个浏览器实例
            if self.local_executable_path:
                browser = await playwright.chromium.launch(headless=self.headless, executable_path=self.local_executable_path)
            else:
                browser = await playwright.chromium.launch(headless=self.headless)
        # 创建一个浏览器上下文，使用指定的 cookie 文件
        context = await browser.new_context(
            viewport={"width": 1600, "height": 900},
            storage_state=f"{self.account_file}"
        )
        try:
            context = await set_init_script(context)

            # 创建一个新的页面
            page = await context.new_page()
            # 访问指定的 URL
            await page.goto("https://creator.xiaohongshu.com/publish/publish?from=homepage&target=video")
            xiaohongshu_logger.info(f'[+]正在上传-------{self.title}.mp4')
            # 等待页面跳转到指定的 URL，没进入，则自动等待到超时
            xiaohongshu_logger.info(f'[-] 正在打开主页...')
            await page.wait_for_url("https://creator.xiaohongshu.com/publish/publish?from=homepage&target=video", timeout=30000)
            # 点击 "上传视频" 按钮
            await page.locator("div[class^='upload-content'] input[class='upload-input']").set_input_files(self.file_path)

            # 等待上传成功标识（状态驱动，无固定 sleep）
            # 视频处理可能较慢，给 10 分钟超时
            try:
                await page.wait_for_function(
                    """
                    () => {
                        const stages = document.querySelectorAll('div.stage');
                        for (const s of stages) {
                            if (s.textContent && s.textContent.includes('上传成功')) return true;
                        }
                        return false;
                    }
                    """,
                    timeout=600_000,  # 10 分钟
                )
                xiaohongshu_logger.info("[+] 检测到上传成功标识!")
            except PlaywrightTimeoutError:
                xiaohongshu_logger.warning("[+] 等待上传成功超时，尝试继续...")

            # 填充标题和话题（等待编辑区域可见后再交互）
            xiaohongshu_logger.info(f'  [-] 正在填充标题和话题...')
            title_container = page.locator(XHS_SELECTORS["title_input"])
            try:
                await title_container.wait_for(state="visible", timeout=8000)
                await title_container.fill(self.title[:30])
            except PlaywrightTimeoutError:
                xiaohongshu_logger.info("  [-] title_input 不可见，尝试备选 notranslate 选择器")
                titlecontainer = page.locator(".notranslate")
                await titlecontainer.wait_for(state="visible", timeout=8000)
                await titlecontainer.click()
                await page.keyboard.press("Control+KeyA")
                await page.keyboard.press("Delete")
                await page.keyboard.type(self.title)
                await page.keyboard.press("Enter")
            css_selector = XHS_SELECTORS["desc_editor"]
            # 等待描述编辑框可见
            await page.wait_for_selector(css_selector, state="visible", timeout=8000)
            if self.desc:
                await page.click(css_selector)
                await page.keyboard.type(self.desc)
                await page.keyboard.press("Enter")
            for index, tag in enumerate(self.tags, start=1):
                await page.type(css_selector, "#" + tag)
                await page.press(css_selector, "Space")
            xiaohongshu_logger.info(f'总共添加{len(self.tags)}个话题')

            if self.is_private:
                try:
                    await page.get_by_text("仅自己可见", exact=False).first.click(timeout=3000)
                    xiaohongshu_logger.info("已尝试设为私密发布")
                except Exception as e:
                    try:
                        await page.locator("label:has-text('私密')").first.click(timeout=2000)
                        xiaohongshu_logger.info("已尝试点击私密选项")
                    except Exception as e2:
                        xiaohongshu_logger.info(f"私密选项未找到或页面已改版: {e}; {e2}")

            # while True:
            #     # 判断重新上传按钮是否存在，如果不存在，代表视频正在上传，则等待
            #     try:
            #         #  新版：定位重新上传
            #         number = await page.locator('[class^="long-card"] div:has-text("重新上传")').count()
            #         if number > 0:
            #             xiaohongshu_logger.success("  [-]视频上传完毕")
            #             break
            #         else:
            #             xiaohongshu_logger.info("  [-] 正在上传视频中...")
            #             await asyncio.sleep(2)

            #             if await page.locator('div.progress-div > div:has-text("上传失败")').count():
            #                 xiaohongshu_logger.error("  [-] 发现上传出错了... 准备重试")
            #                 await self.handle_upload_error(page)
            #     except:
            #         xiaohongshu_logger.info("  [-] 正在上传视频中...")
            #         await asyncio.sleep(2)
            
            # 上传视频封面（cover_path / thumbnail_path 传入本地文件路径时尝试）
            if self.thumbnail_path and os.path.isfile(self.thumbnail_path):
                try:
                    await self.set_thumbnail(page, self.thumbnail_path)
                except Exception as e:
                    xiaohongshu_logger.info(f"封面设置跳过: {e}")

            # 更换可见元素
            # await self.set_location(page, "青岛市")

            # # 頭條/西瓜
            # third_part_element = '[class^="info"] > [class^="first-part"] div div.semi-switch'
            # # 定位是否有第三方平台
            # if await page.locator(third_part_element).count():
            #     # 检测是否是已选中状态
            #     if 'semi-switch-checked' not in await page.eval_on_selector(third_part_element, 'div => div.className'):
            #         await page.locator(third_part_element).locator('input.semi-switch-native-control').click()

            if self.publish_date != 0:
                await self.set_schedule_time_xiaohongshu(page, self.publish_date)

            # 等待发布按钮可见并点击，然后等待跳转成功页
            btn_text = "定时发布" if self.publish_date != 0 else "发布"
            publish_btn = page.locator(XHS_SELECTORS["publish_button"].format(btn_text=btn_text))
            await publish_btn.wait_for(state="visible", timeout=15000)
            # 重试点击，直到成功跳转（平台可能有延迟渲染）
            for _attempt in range(10):
                try:
                    await publish_btn.click()
                    await page.wait_for_url(
                        "https://creator.xiaohongshu.com/publish/success?**",
                        timeout=4000,
                    )
                    xiaohongshu_logger.success("  [-]视频发布成功")
                    break
                except PlaywrightTimeoutError:
                    xiaohongshu_logger.info("  [-] 视频正在发布中，等待跳转...")
            else:
                raise RuntimeError("发布操作超时，请检查页面状态")

            await context.storage_state(path=self.account_file)  # 保存cookie
            xiaohongshu_logger.success('  [-]cookie更新完毕！')
        finally:
            if context:
                await context.close()
            if close_browser_when_done and browser:
                await browser.close()
    
    async def set_thumbnail(self, page: Page, thumbnail_path: str):
        if thumbnail_path:
            await page.click('text="选择封面"')
            # 等待模态框出现（状态驱动，无固定 sleep）
            await page.wait_for_selector("div.semi-modal-content", state="visible", timeout=8000)
            await page.click('text="设置竖封面"')
            # 等待文件上传组件就绪
            upload_input = page.locator(XHS_SELECTORS["thumbnail_upload_input"])
            await upload_input.wait_for(state="attached", timeout=8000)
            await upload_input.set_input_files(thumbnail_path)
            # 等待"完成"按钮可见并点击
            finish_btn = page.locator(XHS_SELECTORS["thumbnail_finish_button"])
            await finish_btn.wait_for(state="visible", timeout=10000)
            await finish_btn.click()

    async def set_location(self, page: Page, location: str = "广州市"):
        print(f"开始设置位置: {location}")
        
        # 点击地点输入框
        print("等待地点输入框加载...")
        loc_ele = await page.wait_for_selector('div.d-text.d-select-placeholder.d-text-ellipsis.d-text-nowrap')
        print(f"已定位到地点输入框: {loc_ele}")
        await loc_ele.click()
        print("点击地点输入框完成")
        
        # 输入位置名称
        print(f"等待1秒后输入位置名称: {location}")
        await page.wait_for_timeout(1000)
        await page.keyboard.type(location)
        print(f"位置名称输入完成: {location}")
        
        # 等待下拉列表加载
        print("等待下拉列表加载...")
        dropdown_selector = 'div.d-popover.d-popover-default.d-dropdown.--size-min-width-large'
        await page.wait_for_timeout(3000)
        try:
            await page.wait_for_selector(dropdown_selector, timeout=3000)
            print("下拉列表已加载")
        except:
            print("下拉列表未按预期显示，可能结构已变化")
        
        # 增加等待时间以确保内容加载完成
        print("额外等待1秒确保内容渲染完成...")
        await page.wait_for_timeout(1000)
        
        # 尝试更灵活的XPath选择器
        print("尝试使用更灵活的XPath选择器...")
        flexible_xpath = (
            f'//div[contains(@class, "d-popover") and contains(@class, "d-dropdown")]'
            f'//div[contains(@class, "d-options-wrapper")]'
            f'//div[contains(@class, "d-grid") and contains(@class, "d-options")]'
            f'//div[contains(@class, "name") and text()="{location}"]'
        )
        await page.wait_for_timeout(3000)
        
        # 尝试定位元素
        print(f"尝试定位包含'{location}'的选项...")
        try:
            # 先尝试使用更灵活的选择器
            location_option = await page.wait_for_selector(
                flexible_xpath,
                timeout=3000
            )
            
            if location_option:
                print(f"使用灵活选择器定位成功: {location_option}")
            else:
                # 如果灵活选择器失败，再尝试原选择器
                print("灵活选择器未找到元素，尝试原始选择器...")
                location_option = await page.wait_for_selector(
                    f'//div[contains(@class, "d-popover") and contains(@class, "d-dropdown")]'
                    f'//div[contains(@class, "d-options-wrapper")]'
                    f'//div[contains(@class, "d-grid") and contains(@class, "d-options")]'
                    f'/div[1]//div[contains(@class, "name") and text()="{location}"]',
                    timeout=2000
                )
            
            # 滚动到元素并点击
            print("滚动到目标选项...")
            await location_option.scroll_into_view_if_needed()
            print("元素已滚动到视图内")
            
            # 增加元素可见性检查
            is_visible = await location_option.is_visible()
            print(f"目标选项是否可见: {is_visible}")
            
            # 点击元素
            print("准备点击目标选项...")
            await location_option.click()
            print(f"成功选择位置: {location}")
            return True
            
        except Exception as e:
            print(f"定位位置失败: {e}")
            
            # 打印更多调试信息
            print("尝试获取下拉列表中的所有选项...")
            try:
                all_options = await page.query_selector_all(
                    '//div[contains(@class, "d-popover") and contains(@class, "d-dropdown")]'
                    '//div[contains(@class, "d-options-wrapper")]'
                    '//div[contains(@class, "d-grid") and contains(@class, "d-options")]'
                    '/div'
                )
                print(f"找到 {len(all_options)} 个选项")
                
                # 打印前3个选项的文本内容
                for i, option in enumerate(all_options[:3]):
                    option_text = await option.inner_text()
                    print(f"选项 {i+1}: {option_text.strip()[:50]}...")
                    
            except Exception as e:
                print(f"获取选项列表失败: {e}")
                
            # 截图保存（取消注释使用）
            # await page.screenshot(path=f"location_error_{location}.png")
            return False

    async def main(self, browser: Browser = None):
        if browser:
            await self.upload(browser=browser)
        else:
            async with async_playwright() as playwright:
                await self.upload(playwright=playwright)


