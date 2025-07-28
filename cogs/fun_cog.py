# cogs/fun_cog.py
import discord
from discord.ext import commands
from discord import app_commands
import random
from utils import checks, ai_utils
import asyncio

# 周易六十四卦基础数据 (保持不变)
# 图片链接来自维基百科，无需自己托管
GUA_DATA = [
    {"id": 1, "name": "乾", "symbol": "䷀", "pinyin": "qián", "desc": "元亨利贞。", "img": "https://upload.wikimedia.org/wikipedia/commons/thumb/1/10/I_Ching_hexagram_01.svg/128px-I_Ching_hexagram_01.svg.png"},
    {"id": 2, "name": "坤", "symbol": "䷁", "pinyin": "kūn", "desc": "元亨，利牝马之贞。君子有攸往，先迷后得主，利。西南得朋，东北丧朋。安贞吉。", "img": "https://upload.wikimedia.org/wikipedia/commons/thumb/8/8b/I_Ching_hexagram_02.svg/128px-I_Ching_hexagram_02.svg.png"},
    {"id": 3, "name": "屯", "symbol": "䷂", "pinyin": "zhūn", "desc": "元亨利贞。勿用有攸往，利建侯。", "img": "https://upload.wikimedia.org/wikipedia/commons/thumb/b/b3/I_Ching_hexagram_03.svg/128px-I_Ching_hexagram_03.svg.png"},
    {"id": 4, "name": "蒙", "symbol": "䷃", "pinyin": "méng", "desc": "亨。匪我求童蒙，童蒙求我。初筮告，再三渎，渎则不告。利贞。", "img": "https://upload.wikimedia.org/wikipedia/commons/thumb/c/c8/I_Ching_hexagram_04.svg/128px-I_Ching_hexagram_04.svg.png"},
    {"id": 5, "name": "需", "symbol": "䷄", "pinyin": "xū", "desc": "有孚，光亨，贞吉。利涉大川。", "img": "https://upload.wikimedia.org/wikipedia/commons/thumb/3/33/I_Ching_hexagram_05.svg/128px-I_Ching_hexagram_05.svg.png"},
    {"id": 6, "name": "讼", "symbol": "䷅", "pinyin": "sòng", "desc": "有孚，窒惕，中吉。终凶。利见大人，不利涉大川。", "img": "https://upload.wikimedia.org/wikipedia/commons/thumb/e/e3/I_Ching_hexagram_06.svg/128px-I_Ching_hexagram_06.svg.png"},
    {"id": 7, "name": "师", "symbol": "䷆", "pinyin": "shī", "desc": "贞，丈人吉，无咎。", "img": "https://upload.wikimedia.org/wikipedia/commons/thumb/4/43/I_Ching_hexagram_07.svg/128px-I_Ching_hexagram_07.svg.png"},
    {"id": 8, "name": "比", "symbol": "䷇", "pinyin": "bǐ", "desc": "吉。原筮元永贞，无咎。不宁方来，后夫凶。", "img": "https://upload.wikimedia.org/wikipedia/commons/thumb/e/e0/I_Ching_hexagram_08.svg/128px-I_Ching_hexagram_08.svg.png"},
    {"id": 9, "name": "小畜", "symbol": "䷈", "pinyin": "xiǎo chù", "desc": "亨。密云不雨，自我西郊。", "img": "https://upload.wikimedia.org/wikipedia/commons/thumb/9/99/I_Ching_hexagram_09.svg/128px-I_Ching_hexagram_09.svg.png"},
    {"id": 10, "name": "履", "symbol": "䷉", "pinyin": "lǚ", "desc": "履虎尾，不咥人，亨。", "img": "https://upload.wikimedia.org/wikipedia/commons/thumb/0/03/I_Ching_hexagram_10.svg/128px-I_Ching_hexagram_10.svg.png"},
    {"id": 11, "name": "泰", "symbol": "䷊", "pinyin": "tài", "desc": "小往大来，吉亨。", "img": "https://upload.wikimedia.org/wikipedia/commons/thumb/d/d5/I_Ching_hexagram_11.svg/128px-I_Ching_hexagram_11.svg.png"},
    {"id": 12, "name": "否", "symbol": "䷋", "pinyin": "pǐ", "desc": "否之匪人，不利君子贞，大往小来。", "img": "https://upload.wikimedia.org/wikipedia/commons/thumb/5/5a/I_Ching_hexagram_12.svg/128px-I_Ching_hexagram_12.svg.png"},
    {"id": 13, "name": "同人", "symbol": "䷌", "pinyin": "tóng rén", "desc": "同人于野，亨。利涉大川，利君子贞。", "img": "https://upload.wikimedia.org/wikipedia/commons/thumb/5/52/I_Ching_hexagram_13.svg/128px-I_Ching_hexagram_13.svg.png"},
    {"id": 14, "name": "大有", "symbol": "䷍", "pinyin": "dà yǒu", "desc": "元亨。", "img": "https://upload.wikimedia.org/wikipedia/commons/thumb/2/2a/I_Ching_hexagram_14.svg/128px-I_Ching_hexagram_14.svg.png"},
    {"id": 15, "name": "谦", "symbol": "䷎", "pinyin": "qiān", "desc": "亨，君子有终。", "img": "https://upload.wikimedia.org/wikipedia/commons/thumb/e/e1/I_Ching_hexagram_15.svg/128px-I_Ching_hexagram_15.svg.png"},
    {"id": 16, "name": "豫", "symbol": "䷏", "pinyin": "yù", "desc": "利建侯行师。", "img": "https://upload.wikimedia.org/wikipedia/commons/thumb/3/35/I_Ching_hexagram_16.svg/128px-I_Ching_hexagram_16.svg.png"},
    {"id": 17, "name": "随", "symbol": "䷐", "pinyin": "suí", "desc": "元亨利贞，无咎。", "img": "https://upload.wikimedia.org/wikipedia/commons/thumb/b/b3/I_Ching_hexagram_17.svg/128px-I_Ching_hexagram_17.svg.png"},
    {"id": 18, "name": "蛊", "symbol": "䷑", "pinyin": "gǔ", "desc": "元亨，利涉大川。先甲三日，后甲三日。", "img": "https://upload.wikimedia.org/wikipedia/commons/thumb/1/17/I_Ching_hexagram_18.svg/128px-I_Ching_hexagram_18.svg.png"},
    {"id": 19, "name": "临", "symbol": "䷒", "pinyin": "lín", "desc": "元亨利贞。至于八月有凶。", "img": "https://upload.wikimedia.org/wikipedia/commons/thumb/4/4e/I_Ching_hexagram_19.svg/128px-I_Ching_hexagram_19.svg.png"},
    {"id": 20, "name": "观", "symbol": "䷓", "pinyin": "guān", "desc": "盥而不荐，有孚颙若。", "img": "https://upload.wikimedia.org/wikipedia/commons/thumb/c/c5/I_Ching_hexagram_20.svg/128px-I_Ching_hexagram_20.svg.png"},
    {"id": 21, "name": "噬嗑", "symbol": "䷔", "pinyin": "shì kè", "desc": "亨。利用狱。", "img": "https://upload.wikimedia.org/wikipedia/commons/thumb/7/73/I_Ching_hexagram_21.svg/128px-I_Ching_hexagram_21.svg.png"},
    {"id": 22, "name": "贲", "symbol": "䷕", "pinyin": "bì", "desc": "亨。小利有攸往。", "img": "https://upload.wikimedia.org/wikipedia/commons/thumb/5/5c/I_Ching_hexagram_22.svg/128px-I_Ching_hexagram_22.svg.png"},
    {"id": 23, "name": "剥", "symbol": "䷖", "pinyin": "bō", "desc": "不利有攸往。", "img": "https://upload.wikimedia.org/wikipedia/commons/thumb/c/c9/I_Ching_hexagram_23.svg/128px-I_Ching_hexagram_23.svg.png"},
    {"id": 24, "name": "复", "symbol": "䷗", "pinyin": "fù", "desc": "亨。出入无疾，朋来无咎。反复其道，七日来复，利有攸往。", "img": "https://upload.wikimedia.org/wikipedia/commons/thumb/8/85/I_Ching_hexagram_24.svg/128px-I_Ching_hexagram_24.svg.png"},
    {"id": 25, "name": "无妄", "symbol": "䷘", "pinyin": "wú wàng", "desc": "元亨利贞。其匪正有眚，不利有攸往。", "img": "https://upload.wikimedia.org/wikipedia/commons/thumb/e/e9/I_Ching_hexagram_25.svg/128px-I_Ching_hexagram_25.svg.png"},
    {"id": 26, "name": "大畜", "symbol": "䷙", "pinyin": "dà chù", "desc": "利贞。不家食吉，利涉大川。", "img": "https://upload.wikimedia.org/wikipedia/commons/thumb/3/36/I_Ching_hexagram_26.svg/128px-I_Ching_hexagram_26.svg.png"},
    {"id": 27, "name": "颐", "symbol": "䷚", "pinyin": "yí", "desc": "贞吉。观颐，自求口实。", "img": "https://upload.wikimedia.org/wikipedia/commons/thumb/8/85/I_Ching_hexagram_27.svg/128px-I_Ching_hexagram_27.svg.png"},
    {"id": 28, "name": "大过", "symbol": "䷛", "pinyin": "dà guò", "desc": "栋桡，利有攸往，亨。", "img": "https://upload.wikimedia.org/wikipedia/commons/thumb/b/b3/I_Ching_hexagram_28.svg/128px-I_Ching_hexagram_28.svg.png"},
    {"id": 29, "name": "坎", "symbol": "䷜", "pinyin": "kǎn", "desc": "习坎，有孚，维心亨，行有尚。", "img": "https://upload.wikimedia.org/wikipedia/commons/thumb/f/f9/I_Ching_hexagram_29.svg/128px-I_Ching_hexagram_29.svg.png"},
    {"id": 30, "name": "离", "symbol": "䷝", "pinyin": "lí", "desc": "利贞，亨。畜牝牛，吉。", "img": "https://upload.wikimedia.org/wikipedia/commons/thumb/c/c7/I_Ching_hexagram_30.svg/128px-I_Ching_hexagram_30.svg.png"},
    {"id": 31, "name": "咸", "symbol": "䷞", "pinyin": "xián", "desc": "亨，利贞。取女吉。", "img": "https://upload.wikimedia.org/wikipedia/commons/thumb/3/3e/I_Ching_hexagram_31.svg/128px-I_Ching_hexagram_31.svg.png"},
    {"id": 32, "name": "恒", "symbol": "䷟", "pinyin": "héng", "desc": "亨，无咎，利贞，利有攸往。", "img": "https://upload.wikimedia.org/wikipedia/commons/thumb/8/88/I_Ching_hexagram_32.svg/128px-I_Ching_hexagram_32.svg.png"},
    {"id": 33, "name": "遁", "symbol": "䷠", "pinyin": "dùn", "desc": "亨，小利贞。", "img": "https://upload.wikimedia.org/wikipedia/commons/thumb/1/18/I_Ching_hexagram_33.svg/128px-I_Ching_hexagram_33.svg.png"},
    {"id": 34, "name": "大壮", "symbol": "䷡", "pinyin": "dà zhuàng", "desc": "利贞。", "img": "https://upload.wikimedia.org/wikipedia/commons/thumb/a/a2/I_Ching_hexagram_34.svg/128px-I_Ching_hexagram_34.svg.png"},
    {"id": 35, "name": "晋", "symbol": "䷢", "pinyin": "jìn", "desc": "康侯用锡马蕃庶，昼日三接。", "img": "https://upload.wikimedia.org/wikipedia/commons/thumb/a/a9/I_Ching_hexagram_35.svg/128px-I_Ching_hexagram_35.svg.png"},
    {"id": 36, "name": "明夷", "symbol": "䷣", "pinyin": "míng yí", "desc": "利艰贞。", "img": "https://upload.wikimedia.org/wikipedia/commons/thumb/5/5f/I_Ching_hexagram_36.svg/128px-I_Ching_hexagram_36.svg.png"},
    {"id": 37, "name": "家人", "symbol": "䷤", "pinyin": "jiā rén", "desc": "利女贞。", "img": "https://upload.wikimedia.org/wikipedia/commons/thumb/1/1a/I_Ching_hexagram_37.svg/128px-I_Ching_hexagram_37.svg.png"},
    {"id": 38, "name": "睽", "symbol": "䷥", "pinyin": "kuí", "desc": "小事吉。", "img": "https://upload.wikimedia.org/wikipedia/commons/thumb/1/11/I_Ching_hexagram_38.svg/128px-I_Ching_hexagram_38.svg.png"},
    {"id": 39, "name": "蹇", "symbol": "䷦", "pinyin": "jiǎn", "desc": "利西南，不利东北。利见大人，贞吉。", "img": "https://upload.wikimedia.org/wikipedia/commons/thumb/f/f0/I_Ching_hexagram_39.svg/128px-I_Ching_hexagram_39.svg.png"},
    {"id": 40, "name": "解", "symbol": "䷧", "pinyin": "xiè", "desc": "利西南。无所往，其来复吉。有攸往，夙吉。", "img": "https://upload.wikimedia.org/wikipedia/commons/thumb/8/87/I_Ching_hexagram_40.svg/128px-I_Ching_hexagram_40.svg.png"},
    {"id": 41, "name": "损", "symbol": "䷨", "pinyin": "sǔn", "desc": "有孚，元吉，无咎，可贞，利有攸往。曷之用？二簋可用享。", "img": "https://upload.wikimedia.org/wikipedia/commons/thumb/c/c3/I_Ching_hexagram_41.svg/128px-I_Ching_hexagram_41.svg.png"},
    {"id": 42, "name": "益", "symbol": "䷩", "pinyin": "yì", "desc": "利有攸往，利涉大川。", "img": "https://upload.wikimedia.org/wikipedia/commons/thumb/6/6e/I_Ching_hexagram_42.svg/128px-I_Ching_hexagram_42.svg.png"},
    {"id": 43, "name": "夬", "symbol": "䷪", "pinyin": "guài", "desc": "扬于王庭，孚号，有厉。告自邑，不利即戎，利有攸往。", "img": "https://upload.wikimedia.org/wikipedia/commons/thumb/b/b3/I_Ching_hexagram_43.svg/128px-I_Ching_hexagram_43.svg.png"},
    {"id": 44, "name": "姤", "symbol": "䷫", "pinyin": "gòu", "desc": "女壮，勿用取女。", "img": "https://upload.wikimedia.org/wikipedia/commons/thumb/3/35/I_Ching_hexagram_44.svg/128px-I_Ching_hexagram_44.svg.png"},
    {"id": 45, "name": "萃", "symbol": "䷬", "pinyin": "cuì", "desc": "亨。王假有庙，利见大人，亨，利贞。用大牲吉，利有攸往。", "img": "https://upload.wikimedia.org/wikipedia/commons/thumb/9/9e/I_Ching_hexagram_45.svg/128px-I_Ching_hexagram_45.svg.png"},
    {"id": 46, "name": "升", "symbol": "䷭", "pinyin": "shēng", "desc": "元亨，用见大人，勿恤，南征吉。", "img": "https://upload.wikimedia.org/wikipedia/commons/thumb/d/d4/I_Ching_hexagram_46.svg/128px-I_Ching_hexagram_46.svg.png"},
    {"id": 47, "name": "困", "symbol": "䷮", "pinyin": "kùn", "desc": "亨，贞，大人吉，无咎。有言不信。", "img": "https://upload.wikimedia.org/wikipedia/commons/thumb/6/69/I_Ching_hexagram_47.svg/128px-I_Ching_hexagram_47.svg.png"},
    {"id": 48, "name": "井", "symbol": "䷯", "pinyin": "jǐng", "desc": "改邑不改井，无丧无得，往来井井。汔至，亦未繘井，羸其瓶，凶。", "img": "https://upload.wikimedia.org/wikipedia/commons/thumb/4/4f/I_Ching_hexagram_48.svg/128px-I_Ching_hexagram_48.svg.png"},
    {"id": 49, "name": "革", "symbol": "䷰", "pinyin": "gé", "desc": "巳日乃孚，元亨利贞，悔亡。", "img": "https://upload.wikimedia.org/wikipedia/commons/thumb/d/d3/I_Ching_hexagram_49.svg/128px-I_Ching_hexagram_49.svg.png"},
    {"id": 50, "name": "鼎", "symbol": "䷱", "pinyin": "dǐng", "desc": "元吉，亨。", "img": "https://upload.wikimedia.org/wikipedia/commons/thumb/b/b3/I_Ching_hexagram_50.svg/128px-I_Ching_hexagram_50.svg.png"},
    {"id": 51, "name": "震", "symbol": "䷲", "pinyin": "zhèn", "desc": "亨。震来虩虩，笑言哑哑。震惊百里，不丧匕鬯。", "img": "https://upload.wikimedia.org/wikipedia/commons/thumb/1/14/I_Ching_hexagram_51.svg/128px-I_Ching_hexagram_51.svg.png"},
    {"id": 52, "name": "艮", "symbol": "䷳", "pinyin": "gèn", "desc": "艮其背，不获其身，行其庭，不见其人，无咎。", "img": "https://upload.wikimedia.org/wikipedia/commons/thumb/f/f2/I_Ching_hexagram_52.svg/128px-I_Ching_hexagram_52.svg.png"},
    {"id": 53, "name": "渐", "symbol": "䷴", "pinyin": "jiàn", "desc": "女归吉，利贞。", "img": "https://upload.wikimedia.org/wikipedia/commons/thumb/4/4a/I_Ching_hexagram_53.svg/128px-I_Ching_hexagram_53.svg.png"},
    {"id": 54, "name": "归妹", "symbol": "䷵", "pinyin": "guī mèi", "desc": "征凶，无攸利。", "img": "https://upload.wikimedia.org/wikipedia/commons/thumb/a/a4/I_Ching_hexagram_54.svg/128px-I_Ching_hexagram_54.svg.png"},
    {"id": 55, "name": "丰", "symbol": "䷶", "pinyin": "fēng", "desc": "亨，王假之，勿忧，宜日中。", "img": "https://upload.wikimedia.org/wikipedia/commons/thumb/b/b7/I_Ching_hexagram_55.svg/128px-I_Ching_hexagram_55.svg.png"},
    {"id": 56, "name": "旅", "symbol": "䷷", "pinyin": "lǚ", "desc": "小亨，旅贞吉。", "img": "https://upload.wikimedia.org/wikipedia/commons/thumb/c/ca/I_Ching_hexagram_56.svg/128px-I_Ching_hexagram_56.svg.png"},
    {"id": 57, "name": "巽", "symbol": "䷸", "pinyin": "xùn", "desc": "小亨，利有攸往，利见大人。", "img": "https://upload.wikimedia.org/wikipedia/commons/thumb/1/13/I_Ching_hexagram_57.svg/128px-I_Ching_hexagram_57.svg.png"},
    {"id": 58, "name": "兑", "symbol": "䷹", "pinyin": "duì", "desc": "亨，利贞。", "img": "https://upload.wikimedia.org/wikipedia/commons/thumb/6/6f/I_Ching_hexagram_58.svg/128px-I_Ching_hexagram_58.svg.png"},
    {"id": 59, "name": "涣", "symbol": "䷺", "pinyin": "huàn", "desc": "亨。王假有庙，利涉大川，利贞。", "img": "https://upload.wikimedia.org/wikipedia/commons/thumb/c/c8/I_Ching_hexagram_59.svg/128px-I_Ching_hexagram_59.svg.png"},
    {"id": 60, "name": "节", "symbol": "䷻", "pinyin": "jié", "desc": "亨。苦节不可贞。", "img": "https://upload.wikimedia.org/wikipedia/commons/thumb/a/a2/I_Ching_hexagram_60.svg/128px-I_Ching_hexagram_60.svg.png"},
    {"id": 61, "name": "中孚", "symbol": "䷼", "pinyin": "zhōng fú", "desc": "豚鱼吉，利涉大川，利贞。", "img": "https://upload.wikimedia.org/wikipedia/commons/thumb/f/f9/I_Ching_hexagram_61.svg/128px-I_Ching_hexagram_61.svg.png"},
    {"id": 62, "name": "小过", "symbol": "䷽", "pinyin": "xiǎo guò", "desc": "亨，利贞。可小事，不可大事。飞鸟遗之音，不宜上，宜下，大吉。", "img": "https://upload.wikimedia.org/wikipedia/commons/thumb/e/e3/I_Ching_hexagram_62.svg/128px-I_Ching_hexagram_62.svg.png"},
    {"id": 63, "name": "既济", "symbol": "䷾", "pinyin": "jì jì", "desc": "亨，小利贞，初吉终乱。", "img": "https://upload.wikimedia.org/wikipedia/commons/thumb/2/23/I_Ching_hexagram_63.svg/128px-I_Ching_hexagram_63.svg.png"},
    {"id": 64, "name": "未济", "symbol": "䷿", "pinyin": "wèi jì", "desc": "亨，小狐汔济，濡其尾，无攸利。", "img": "https://upload.wikimedia.org/wikipedia/commons/thumb/d/d5/I_Ching_hexagram_64.svg/128px-I_Ching_hexagram_64.svg.png"}
]

class FunCog(commands.Cog, name="娱乐功能"):
    """包含占卜、互动等娱乐性指令"""
    def __init__(self, bot: commands.Bot):
        self.bot = bot

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
            
            # 构造AI请求，使用当前人格
            messages = [
                {"role": "user", "content": "主人温柔地抚摸了我的头，请用你的人格和风格来回应这个动作。要体现被抚摸时的感受和反应。"}
            ]
            
            try:
                ai_response = await ai_utils.call_ai(messages, temperature=0.8, max_tokens=200, context_for_error_dm="摸头互动")
                if ai_response == ai_utils.INTERNAL_AI_ERROR_SIGNAL:
                    response = "喵~ 主人的手好温暖呢！(蹭蹭)"
                else:
                    response = ai_response.strip()
            except Exception as e:
                print(f"AI摸头调用失败: {e}")
                response = "喵~ 主人的手好温暖呢！(蹭蹭)"
            
            await ctx.send(response)
        elif 项目 == "hug":
            await ctx.defer()
            
            from utils import ai_utils
            
            # 构造AI请求，使用当前人格
            messages = [
                {"role": "user", "content": "主人给了我一个温暖的拥抱，请用你的人格和风格来回应这个拥抱。要体现被拥抱时的感受、情感和反应。"}
            ]
            
            try:
                ai_response = await ai_utils.call_ai(messages, temperature=0.8, max_tokens=200, context_for_error_dm="抱抱互动")
                if ai_response == ai_utils.INTERNAL_AI_ERROR_SIGNAL:
                    response = "主人！我也要抱抱你！(紧紧抱住主人)"
                else:
                    response = ai_response.strip()
            except Exception as e:
                print(f"AI抱抱调用失败: {e}")
                response = "主人！我也要抱抱你！(紧紧抱住主人)"
            
            await ctx.send(response)
        elif 项目 == "kiss":
            await ctx.defer()
            
            from utils import ai_utils
            
            # 构造AI请求，使用当前人格
            messages = [
                {"role": "user", "content": "主人给了我一个温柔的亲亲，请用你的人格和风格来回应这个亲亲。要体现被亲亲时的害羞、幸福和反应。"}
            ]
            
            try:
                ai_response = await ai_utils.call_ai(messages, temperature=0.8, max_tokens=200, context_for_error_dm="亲亲互动")
                if ai_response == ai_utils.INTERNAL_AI_ERROR_SIGNAL:
                    response = "呜...主人亲我了！好害羞好幸福！(脸红)"
                else:
                    response = ai_response.strip()
            except Exception as e:
                print(f"AI亲亲调用失败: {e}")
                response = "呜...主人亲我了！好害羞好幸福！(脸红)"
            
            await ctx.send(response)
        elif 项目 == "pet":
            await ctx.defer()
            
            from utils import ai_utils
            
            # 构造AI请求，使用当前人格
            messages = [
                {"role": "user", "content": "主人温柔地抚摸了我，请用你的人格和风格来回应这个抚摸。要体现被抚摸时的舒适、放松和反应。"}
            ]
            
            try:
                ai_response = await ai_utils.call_ai(messages, temperature=0.8, max_tokens=200, context_for_error_dm="抚摸互动")
                if ai_response == ai_utils.INTERNAL_AI_ERROR_SIGNAL:
                    response = "喵呜~ 主人的手好温柔，摸得我好舒服~"
                else:
                    response = ai_response.strip()
            except Exception as e:
                print(f"AI抚摸调用失败: {e}")
                response = "喵呜~ 主人的手好温柔，摸得我好舒服~"
            
            await ctx.send(response)
        elif 项目 == "feed":
            await ctx.defer()
            
            from utils import ai_utils
            
            # 构造AI请求，使用当前人格
            messages = [
                {"role": "user", "content": "主人给我喂了美味的食物，请用你的人格和风格来回应这个喂食。要体现被喂食时的开心、感激和反应。"}
            ]
            
            try:
                ai_response = await ai_utils.call_ai(messages, temperature=0.8, max_tokens=200, context_for_error_dm="喂食互动")
                if ai_response == ai_utils.INTERNAL_AI_ERROR_SIGNAL:
                    response = "哇！主人给我好吃的！谢谢主人！(开心地摇尾巴)"
                else:
                    response = ai_response.strip()
            except Exception as e:
                print(f"AI喂食调用失败: {e}")
                response = "哇！主人给我好吃的！谢谢主人！(开心地摇尾巴)"
            
            await ctx.send(response)
        elif 项目 == "play":
            await ctx.defer()
            
            from utils import ai_utils
            
            # 构造AI请求，使用当前人格
            messages = [
                {"role": "user", "content": "主人要和我一起玩耍，请用你的人格和风格来回应这个玩耍邀请。要体现被邀请玩耍时的兴奋、期待和反应。"}
            ]
            
            try:
                ai_response = await ai_utils.call_ai(messages, temperature=0.8, max_tokens=200, context_for_error_dm="玩耍互动")
                if ai_response == ai_utils.INTERNAL_AI_ERROR_SIGNAL:
                    response = "耶！主人要和我玩！我最喜欢和主人一起玩了！(兴奋地跳来跳去)"
                else:
                    response = ai_response.strip()
            except Exception as e:
                print(f"AI玩耍调用失败: {e}")
                response = "耶！主人要和我玩！我最喜欢和主人一起玩了！(兴奋地跳来跳去)"
            
            await ctx.send(response)

    @commands.hybrid_command(name="卜卦", description="让米尔可为你卜一卦，窥探天机。")
    async def divination(self, ctx: commands.Context):
        import random
        gua_list = [
            ("乾卦", "天行健，君子以自强不息。代表积极进取、刚健有为。"),
            ("坤卦", "地势坤，君子以厚德载物。代表包容、顺应、承载。"),
            ("屯卦", "云雷屯，君子以经纶。代表艰难起步、万事开头难。"),
            ("蒙卦", "山水蒙，君子以果行育德。代表启蒙、成长、求知。"),
            ("需卦", "云上于天，需君子以饮食宴乐。代表等待时机、蓄势待发。"),
            ("讼卦", "天水讼，君子以作事谋始。代表争执、诉讼、分歧。"),
            ("师卦", "地水师，君子以容民畜众。代表团队、组织、领导。"),
            ("比卦", "水地比，君子以朋友讲习。代表亲近、合作、团结。"),
            ("小畜卦", "风天小畜，君子以懿文德。代表积蓄、克制、等待。"),
            ("履卦", "天泽履，君子以辨上下、定民志。代表谨慎行事、循序渐进。")
        ]
        gua, interpretation = random.choice(gua_list)
        await ctx.send(f"你抽到的卦象是：**{gua}**\n解读：{interpretation}")

async def setup(bot: commands.Bot):
    await bot.add_cog(FunCog(bot))