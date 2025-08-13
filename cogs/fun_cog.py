# cogs/fun_cog.py
import discord
from discord.ext import commands
from discord import app_commands
import random
import re
from utils import checks, ai_utils, emoji_manager
from typing import List, Dict, Any
import asyncio

# --- 持久化视图定义 (无状态设计) ---

class EmojiNavigationView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    async def update_page(self, interaction: discord.Interaction, new_page: int):
        """通用页面更新逻辑"""
        embed = interaction.message.embeds
        
        # 从 footer 解析总页数
        try:
            footer_text = embed.footer.text
            # 正则表达式匹配 "第 x/y 页"
            match = re.search(r'第 (\d+)/(\d+) 页', footer_text)
            if not match:
                raise ValueError("Footer format invalid")
            current_page, max_pages = map(int, match.groups())
        except (AttributeError, ValueError, TypeError):
            await interaction.response.send_message("❌ 无法解析页面信息，请重新发起搜索。", ephemeral=True)
            return

        # 从 title 解析关键词
        keyword = None
        if embed.title and "“" in embed.title:
            keyword_match = re.search(r'“(.+?)”', embed.title)
            if keyword_match:
                keyword = keyword_match.group(1)

        # 重新生成 embed
        new_embed = await FunCog.create_emoji_embed(self, page_num=new_page, keyword=keyword)
        
        # 更新按钮状态
        for item in self.children:
            if isinstance(item, discord.ui.Button):
                if item.custom_id == "emoji_prev_page":
                    item.disabled = (new_page == 1)
                elif item.custom_id == "emoji_next_page":
                    item.disabled = (new_page == max_pages)
        
        await interaction.response.edit_message(embed=new_embed, view=self)

    @discord.ui.button(label="上一页", style=discord.ButtonStyle.secondary, custom_id="emoji_prev_page")
    async def prev_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        footer_text = interaction.message.embeds.footer.text
        match = re.search(r'第 (\d+)/(\d+) 页', footer_text)
        current_page, _ = map(int, match.groups())
        await self.update_page(interaction, current_page - 1)

    @discord.ui.button(label="下一页", style=discord.ButtonStyle.secondary, custom_id="emoji_next_page")
    async def next_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        footer_text = interaction.message.embeds.footer.text
        match = re.search(r'第 (\d+)/(\d+) 页', footer_text)
        current_page, _ = map(int, match.groups())
        await self.update_page(interaction, current_page + 1)


# --- Cog 定义 ---

class FunCog(commands.Cog, name="娱乐功能"):
    """包含占卜、互动等娱乐性指令"""
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def create_emoji_embed(self, page_num: int, keyword: str = None) -> discord.Embed:
        """静态方法，用于创建表情列表的 Embed"""
        all_emojis_dict = emoji_manager.get_all_emojis()
        
        if keyword:
            keyword_lower = keyword.lower()
            filtered_emojis = [
                data for data in all_emojis_dict.values()
                if keyword_lower in data['name'].lower() or (data.get('description') and keyword_lower in data['description'].lower())
            ]
        else:
            filtered_emojis = list(all_emojis_dict.values())
        
        filtered_emojis.sort(key=lambda x: x['name'])
        
        max_pages = (len(filtered_emojis) - 1) // 25 + 1
        if max_pages == 0: max_pages = 1

        start_index = (page_num - 1) * 25
        end_index = start_index + 25
        page_emojis = filtered_emojis[start_index:end_index]

        title = f"表情搜索结果 for “{keyword}”" if keyword else "所有表情"
        embed = discord.Embed(title=title, color=discord.Color.blue())
        
        description = ""
        if page_emojis:
            for emoji_data in page_emojis:
                is_animated = emoji_data.get('animated', False)
                emoji_id = emoji_data['id']
                emoji_name = emoji_data['name']
                emoji_str = f"<{'a' if is_animated else ''}:{emoji_name}:{emoji_id}>"
                description += f"{emoji_str} `:{emoji_name}:`\n"
        else:
            description = "没有找到结果。"
            
        embed.description = description
        embed.set_footer(text=f"第 {page_num}/{max_pages} 页")
        return embed

    @commands.hybrid_command(name="寻找表情", description="搜索机器人所有服务器中的表情。")
    @app_commands.describe(keyword="要搜索的表情名称或描述关键词（可选）。")
    async def find_emoji(self, ctx: commands.Context, keyword: str = None):
        await ctx.defer(ephemeral=True)

        all_emojis_dict = emoji_manager.get_all_emojis()
        if not all_emojis_dict:
            await ctx.send("表情库为空，请先使用 `/crawl emojis` 指令更新。", ephemeral=True)
            return

        embed = await self.create_emoji_embed(page_num=1, keyword=keyword)
        
        # 从 footer 解析总页数以设置按钮初始状态
        footer_text = embed.footer.text
        match = re.search(r'第 (\d+)/(\d+) 页', footer_text)
        _, max_pages = map(int, match.groups())

        view = EmojiNavigationView()
        for item in view.children:
            if isinstance(item, discord.ui.Button):
                if item.custom_id == "emoji_prev_page":
                    item.disabled = True
                elif item.custom_id == "emoji_next_page":
                    item.disabled = (max_pages == 1)

        await ctx.send(embed=embed, view=view, ephemeral=True)

    # ... (保留原有的 娱乐 和 卜卦 指令)
    @commands.hybrid_command(name="娱乐", description="娱乐互动合集")
    @app_commands.describe(
        项目="选择娱乐项目"
    )
    @app_commands.choices(
        项目=[
            app_commands.Choice(name="摸头", value="pathead"),
            app_commands.Choice(name="抱抱", value="hug"),
            app_commands.Choice(name="亲亲", value="kiss"),
            app_commands.Choice(name="摸摸", value="pet"),
            app_commands.Choice(name="喂食", value="feed"),
            app_commands.Choice(name="玩耍", value="play"),
        ]
    )
    async def fun(self, ctx: commands.Context, 项目: str):
        if 项目 == "pathead":
            await ctx.defer()
            
            from utils import ai_utils
            
            messages = [{"role": "user", "content": "主人温柔地抚摸了我的头，请用你的人格和风格来回应这个动作。要体现被抚摸时的感受和反应。"}]
            
            try:
                ai_response = await ai_utils.call_ai(messages, temperature=0.8, max_tokens=200, context_for_error_dm="摸头互动")
                response = ai_response.strip() if ai_response != ai_utils.INTERNAL_AI_ERROR_SIGNAL else "喵~ 主人的手好温暖呢！(蹭蹭)"
            except Exception as e:
                print(f"AI摸头调用失败: {e}")
                response = "喵~ 主人的手好温暖呢！(蹭蹭)"
            
            await ctx.send(response)
        elif 项目 == "hug":
            await ctx.defer()
            from utils import ai_utils
            messages = [{"role": "user", "content": "主人给了我一个温暖的拥抱，请用你的人格和风格来回应这个拥抱。要体现被拥抱时的感受、情感和反应。"}]
            try:
                ai_response = await ai_utils.call_ai(messages, temperature=0.8, max_tokens=200, context_for_error_dm="抱抱互动")
                response = ai_response.strip() if ai_response != ai_utils.INTERNAL_AI_ERROR_SIGNAL else "主人！我也要抱抱你！(紧紧抱住主人)"
            except Exception as e:
                print(f"AI抱抱调用失败: {e}")
                response = "主人！我也要抱抱你！(紧紧抱住主人)"
            await ctx.send(response)
        # ... (其他娱乐项目逻辑)

    @commands.hybrid_command(name="卜卦", description="让米尔可为你卜一卦，窥探天机。")
    async def divination(self, ctx: commands.Context):
        gua, interpretation = random.choice(GUA_DATA)
        await ctx.send(f"你抽到的卦象是：**{gua['name']}**\n解读：{gua['desc']}")


async def setup(bot: commands.Bot):
    bot.add_view(EmojiNavigationView())
    await bot.add_cog(FunCog(bot))