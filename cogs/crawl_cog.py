# cogs/crawl_cog.py
import discord
from discord.ext import commands
from discord import app_commands
from typing import Optional
from utils import checks, ai_utils
import asyncio
import json
import io
import time
import os

class CrawlCog(commands.Cog, name="爬取工具"):
    """专门用于爬取服务器消息的工具"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.is_crawling = False

    async def _crawl_task(self, ctx: commands.Context, channels_to_crawl: list, user: Optional[discord.User], limit: Optional[int], format: str):
        """后台执行的爬虫任务"""
        self.is_crawling = True
        start_time = time.time()
        last_report_time = start_time
        
        owner_id = int(os.getenv('BOT_OWNER_ID', 0))
        owner = await self.bot.fetch_user(owner_id)

        try:
            messages = []
            total_channels = len(channels_to_crawl)
            processed_channels = 0

            for current_channel in channels_to_crawl:
                processed_channels += 1
                
                # 每隔5分钟汇报一次进度
                current_time = time.time()
                if current_time - last_report_time >= 300: # 5 minutes
                    last_report_time = current_time
                    progress_percent = int((processed_channels / total_channels) * 100)
                    elapsed_minutes = int((current_time - start_time) / 60)
                    try:
                        await ctx.channel.send(
                            f"⏳ 爬虫任务仍在后台运行中...\n"
                            f"进度: {progress_percent}% ({processed_channels}/{total_channels} 频道)\n"
                            f"已收集: {len(messages)} 条消息\n"
                            f"已耗时: {elapsed_minutes} 分钟",
                            delete_after=60 # 临时消息，60秒后自动删除
                        )
                    except Exception as e:
                        print(f"无法发送进度报告: {e}")

                try:
                    async for msg in current_channel.history(limit=limit):
                        if user and msg.author.id != user.id:
                            continue
                        if msg.author.bot:
                            continue

                        if format == "简洁":
                            msg_data = {"t": msg.content, "ts": int(msg.created_at.timestamp())}
                        elif format == "详细":
                            attachments = [{"name": att.filename, "url": att.url, "size": att.size} for att in msg.attachments]
                            embeds = [emb.to_dict() for emb in msg.embeds]
                            msg_data = {
                                "c": current_channel.name, 
                                "u": msg.author.name,
                                "uid": msg.author.id,
                                "t": msg.content, 
                                "ts": int(msg.created_at.timestamp())
                            }
                            if attachments: msg_data["a"] = attachments
                            if embeds: msg_data["e"] = embeds
                        elif format == "向量化":
                            # 准备用于向量化的文本
                            formatted_timestamp = msg.created_at.strftime("%Y-%m-%d %H:%M:%S")
                            text_to_embed = f"[{formatted_timestamp}] {msg.author.name}: {msg.content}"
                            
                            # 调用API获取向量
                            embedding = await ai_utils.get_text_embedding(text_to_embed)
                            
                            # 如果成功获取，则保存精简后的数据
                            if embedding:
                                msg_data = {
                                    "vector": embedding,
                                    "original_timestamp": int(msg.created_at.timestamp())
                                }
                                messages.append(msg_data)
                                # 短暂休眠以避免API速率限制
                                await asyncio.sleep(0.05)
                            else:
                                print(f"跳过一条消息，因为它无法被向量化: {text_to_embed[:50]}...")

                except discord.Forbidden:
                    continue
                except Exception as e:
                    print(f"爬取频道 {current_channel.name} 时出错: {e}")
                    continue
            
            # 任务完成，打包并发送文件
            if not messages:
                await owner.send("主人，后台爬虫任务已完成，但未收集到任何符合条件的消息。")
                return

            file_content = json.dumps(messages, ensure_ascii=False, indent=2)
            file_bytes = io.BytesIO(file_content.encode('utf-8'))
            
            user_str = f"_{user.name}" if user else ""
            channel_str = f"_{channels_to_crawl[0].name}" if len(channels_to_crawl) == 1 else ""
            filename = f"crawl_data_{ctx.guild.name}{channel_str}{user_str}_{format}.json"

            await owner.send(
                f"主人，后台爬虫任务已完成！\n"
                f"服务器: `{ctx.guild.name}`\n"
                f"总共收集到 `{len(messages)}` 条消息。",
                file=discord.File(file_bytes, filename=filename)
            )

        except Exception as e:
            try:
                await owner.send(f"主人，后台爬虫任务发生严重错误并已终止: `{e}`")
            except Exception as send_e:
                print(f"向主人报告爬虫错误时再次失败: {send_e}")
        finally:
            self.is_crawling = False

    @commands.hybrid_command(name="crawl", description="[主人] 爬取服务器发言，可指定频道、用户。")
    @app_commands.describe(
        channel="要爬取的目标频道（留空则爬取所有频道）",
        user="要爬取的目标用户（留空则爬取所有人）",
        limit="每个频道最多收集多少条消息（0为无限制）",
        format="输出格式"
    )
    @app_commands.choices(format=[
        app_commands.Choice(name="简洁", value="简洁"),
        app_commands.Choice(name="详细", value="详细"),
        app_commands.Choice(name="向量化", value="向量化")
    ])
    @commands.check(checks.is_owner)
    async def crawl(self, ctx: commands.Context, channel: Optional[discord.TextChannel] = None, user: Optional[discord.User] = None, limit: Optional[int] = 0, format: Optional[str] = "详细"):
        """爬取服务器发言记录"""
        await ctx.defer(ephemeral=True)

        if not ctx.guild:
            await ctx.send("❌ 此命令只能在服务器内使用。", ephemeral=True)
            return
            
        if self.is_crawling:
            await ctx.send("❌ 已有一个爬虫任务正在后台运行，请等待其完成后再试。", ephemeral=True)
            return

        channels_to_crawl = [channel] if channel else ctx.guild.text_channels
        if not channels_to_crawl:
            await ctx.send("❌ 未找到可爬取的频道。", ephemeral=True)
            return

        history_limit = limit if (limit is not None and limit > 0) else None

        # 启动后台任务
        asyncio.create_task(self._crawl_task(ctx, channels_to_crawl, user, history_limit, format))

        await ctx.send("✅ 命令已收到！爬虫任务已在后台启动。\n完成后，结果将通过私信发送给您。", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(CrawlCog(bot))
