# cogs/general_cog.py
import discord
from discord.ext import commands
from discord import app_commands
import time
import os
import re
from datetime import datetime
from utils import ai_utils, data_manager, checks, emoji_manager

# --- 模态框定义 ---

class ProxyReplyModal(discord.ui.Modal, title="伪装回复"):
    def __init__(self, target_message: discord.Message):
        super().__init__()
        self.target_message = target_message
        
        self.content_input = discord.ui.TextInput(
            label="消息内容",
            style=discord.TextStyle.paragraph,
            default=target_message.content,
            required=True,
            max_length=2000,
        )
        self.add_item(self.content_input)

    async def on_submit(self, interaction: discord.Interaction):
        content = self.content_input.value
        all_emojis = emoji_manager.get_all_emojis()
        def replace_emoji(match):
            emoji_name = match.group(1)
            for emoji_data in all_emojis.values():
                if emoji_data['name'].lower() == emoji_name.lower():
                    is_animated = emoji_data.get('animated', False)
                    emoji_id = emoji_data['id']
                    return f"<{'a' if is_animated else ''}:{emoji_name}:{emoji_id}>"
            return f":{emoji_name}:"
        processed_content = re.sub(r':(\w+):', replace_emoji, content)

        try:
            reference = self.target_message.to_reference(fail_if_not_exists=False)
            await self.target_message.channel.send(processed_content, reference=reference)
            await interaction.response.send_message("✅ 回复已发送！", ephemeral=True, delete_after=5)
        except Exception as e:
            await interaction.response.send_message(f"❌ 发送失败: {e}", ephemeral=True, delete_after=10)


# --- Cog 定义 ---

class GeneralCog(commands.Cog, name="通用指令"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        
        self.proxy_reply_context_menu = app_commands.ContextMenu(
            name='以此消息伪装回复',
            callback=self.proxy_reply_callback,
        )
        self.bot.tree.add_command(self.proxy_reply_context_menu)

    @app_commands.check(checks.is_owner)
    async def proxy_reply_callback(self, interaction: discord.Interaction, message: discord.Message):
        modal = ProxyReplyModal(target_message=message)
        await interaction.response.send_modal(modal)


    @commands.hybrid_command(name="服务状态", description="检查米尔可的各项服务状态及延迟。")
    async def servicestatus(self, ctx: commands.Context):
        await ctx.defer()
        
        discord_latency = round(self.bot.latency * 1000)
        start_time_ai = time.time()
        ai_test_messages = [{"role": "user", "content": "ping"}]
        ai_response = await ai_utils.call_ai(ai_test_messages, temperature=0.1, max_tokens=10, context_for_error_dm="Ping指令测试")
        end_time_ai = time.time()
        ai_latency = round((end_time_ai - start_time_ai) * 1000)
        ai_status = "🟢 正常" if ai_response != ai_utils.INTERNAL_AI_ERROR_SIGNAL else "🔴 异常"
        
        hf_status = "N/A"
        if os.getenv('HF_TOKEN') and os.getenv('HF_DATA_REPO_ID'):
            start_time_hf = time.time()
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

        if ai_status == "🟢 正常" and hf_status != "🔴 异常":
            overall_status = "💚 **所有核心服务运转良好**"
            color = discord.Color.green()
        else:
            overall_status = "💔 **部分核心服务存在异常，我可能无法完整回应！**"
            color = discord.Color.red()
            
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

    @commands.hybrid_command(name="伪装发言", description="以bot的身份在当前频道发送消息。")
    @app_commands.describe(
        content="要发送的内容，可使用 :表情名: 来插入表情。",
        reply_to="要回复的消息ID（可选）。",
        target_user="要@的目标用户（可选）。"
    )
    async def proxy(self, ctx: commands.Context, content: str, reply_to: str = None, target_user: discord.User = None):
        # 这是一个公开指令，但为了防止滥用，可以考虑加入一些限制，例如冷却时间
        # commands.cooldown(1, 5, commands.BucketType.user)

        if ctx.interaction:
            await ctx.interaction.response.send_message("正在处理您的消息...", ephemeral=True, delete_after=2)

        all_emojis = emoji_manager.get_all_emojis()
        def replace_emoji(match):
            emoji_name = match.group(1)
            for emoji_data in all_emojis.values():
                if emoji_data['name'].lower() == emoji_name.lower():
                    is_animated = emoji_data.get('animated', False)
                    emoji_id = emoji_data['id']
                    return f"<{'a' if is_animated else ''}:{emoji_name}:{emoji_id}>"
            return f":{emoji_name}:"
        processed_content = re.sub(r':(\w+):', replace_emoji, content)

        if target_user:
            processed_content = f"{target_user.mention} {processed_content}"

        try:
            if ctx.message:
                await ctx.message.delete()
        except (discord.Forbidden, discord.NotFound):
            pass

        target_channel = ctx.channel
        reference = None
        if reply_to:
            try:
                message_id = int(reply_to)
                message_to_reply = await target_channel.fetch_message(message_id)
                reference = message_to_reply.to_reference(fail_if_not_exists=False)
            except (ValueError, discord.NotFound, discord.Forbidden):
                # 对于公开指令，错误提示应更通用，或不提示
                pass

        await target_channel.send(processed_content, reference=reference)


async def setup(bot: commands.Bot):
    await bot.add_cog(GeneralCog(bot))