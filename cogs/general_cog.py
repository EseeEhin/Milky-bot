# cogs/general_cog.py
import discord
from discord.ext import commands
import time
import os
from datetime import datetime
from utils import ai_utils, data_manager

class GeneralCog(commands.Cog, name="通用指令"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_command(name="服务状态", description="检查米尔可的各项服务状态及延迟。")
    async def servicestatus(self, ctx: commands.Context):
        """增强版的ping指令，检查多个服务状态"""
        await ctx.defer()
        
        # 1. Discord Websocket 延迟
        discord_latency = round(self.bot.latency * 1000)
        
        # 2. AI 核心连接测试
        start_time_ai = time.time()
        # 发送一个极简的、不会出错的请求
        ai_test_messages = [{"role": "user", "content": "ping"}]
        ai_response = await ai_utils.call_ai(ai_test_messages, temperature=0.1, max_tokens=10, context_for_error_dm="Ping指令测试")
        end_time_ai = time.time()
        ai_latency = round((end_time_ai - start_time_ai) * 1000)
        ai_status = "🟢 正常" if ai_response != ai_utils.INTERNAL_AI_ERROR_SIGNAL else "🔴 异常"
        
        # 3. 数据持久化服务测试
        hf_status = "N/A"
        if os.getenv('HF_TOKEN') and os.getenv('HF_DATA_REPO_ID'):
            start_time_hf = time.time()
            # 仅保存，不加载，作为测试
            try:
                data_manager.save_data_to_hf()
                hf_status = "🟢 正常"
            except Exception:
                hf_status = "🔴 异常"
            end_time_hf = time.time()
            hf_latency = round((end_time_hf - start_time_hf) * 1000)
        else:
            hf_status = "⚪ 未配置"
            hf_latency = "N/A"

        # 4. 综合评价
        if ai_status == "🟢 正常" and hf_status != "🔴 异常":
            overall_status = "💚 **所有核心服务运转良好**"
            color = discord.Color.green()
        else:
            overall_status = "💔 **部分核心服务存在异常，我可能无法完整回应！**"
            color = discord.Color.red()
            
        # 构造 Embed
        embed = discord.Embed(
            title="米尔可状态诊断报告",
            description=overall_status,
            color=color
        )
        embed.add_field(name="🛰️ Discord 网关延迟", value=f"`{discord_latency} ms`", inline=True)
        embed.add_field(name="🧠 AI 核心响应", value=f"`{ai_latency} ms`\n状态: **{ai_status}**", inline=True)
        embed.add_field(name="💾 数据持久化 (HF)", value=f"`{hf_latency} ms`\n状态: **{hf_status}**", inline=True)
        
        embed.set_footer(text=f"诊断于: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        await ctx.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(GeneralCog(bot))