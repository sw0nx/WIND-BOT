import os
import discord
from discord.ext import commands

TOKEN = os.getenv("BOT_TOKEN")  # Zeabur 환경 변수로 BOT_TOKEN 등록

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

class TicketSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="문의", description="일반 문의 티켓 열기"),
            discord.SelectOption(label="신고", description="신고 티켓 열기"),
            discord.SelectOption(label="기타", description="기타 티켓 열기")
        ]
        super().__init__(placeholder="티켓 항목 선택", options=options)

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_message(
            f"'{self.values[0]}' 티켓을 생성합니다!",
            ephemeral=True
        )

class TicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(TicketSelect())

@bot.command()
async def 티켓(ctx):
    await ctx.send(
        "아래 드롭다운 중 하나를 선택해 티켓을 열어주세요.\n티켓에서 맨션 시 티켓 닫습니다.",
        view=TicketView()
    )

@bot.event
async def on_ready():
    print(f"✅ 봇 로그인됨: {bot.user}")

bot.run(TOKEN)
