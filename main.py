import os
import discord
from discord import app_commands
from discord.ext import commands

TOKEN = os.getenv("BOT_TOKEN")

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

@app_commands.command(name="테스트", description="컴포넌트 V2 드롭다운 테스트")
async def test_cmd(interaction: discord.Interaction):
    components_v2 = [
        {
            "type": 1,  # ActionRow
            "components": [
                {
                    "type": 3,  # StringSelectMenu
                    "custom_id": "test_select_v2",
                    "placeholder": "항목 선택",
                    "options": [
                        {"label": "옵션 1", "value": "opt1"},
                        {"label": "옵션 2", "value": "opt2"}
                    ]
                }
            ]
        }
    ]

    await interaction.response.send_message(
        content="아래 드롭다운에서 선택해 주세요.",
        components=components_v2,
        flags=discord.MessageFlags.is_components_v2()
    )

@bot.event
async def on_interaction(interaction: discord.Interaction):
    if interaction.type == discord.InteractionType.component:
        if interaction.data.get("custom_id") == "test_select_v2":
            selected = interaction.data["values"][0]
            await interaction.response.send_message(f"선택한 값: `{selected}`", ephemeral=True)

@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"✅ 봇 로그인: {bot.user}")

bot.run(TOKEN)
