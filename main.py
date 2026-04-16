import discord
from discord.ext import commands
import asyncio
import os
from config import TOKEN, PREFIX
from music_cog import MusicCog

# Configuração do bot
intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True

bot = commands.Bot(command_prefix=PREFIX, intents=intents, help_command=None)

# Dicionário para armazenar resultados de busca
bot.search_results = {}

@bot.event
async def on_ready():
    print(f'✅ Bot conectado como {bot.user.name}')
    print(f'📊 Comandos configurados com prefixo: {PREFIX}')
    await bot.change_presence(activity=discord.Activity(
        type=discord.ActivityType.listening,
        name=f"{PREFIX}p | {PREFIX}help"
    ))

@bot.command(name='help')
async def custom_help(ctx):
    """Mostra todos os comandos disponíveis"""
    from config import COMMANDS
    
    embed = discord.Embed(
        title="🎵 Comandos do Bot de Música",
        description=f"Prefixo atual: `{PREFIX}`",
        color=discord.Color.purple()
    )
    
    commands_info = {
        "p": "Toca música do YouTube, Spotify, SoundCloud, Deezer ou link direto",
        "stop": "Para a música e limpa a fila",
        "pause": "Pausa a música atual",
        "resume": "Continua a música pausada",
        "skip": "Pula para a próxima música",
        "queue": "Mostra a fila de músicas",
        "clear": "Limpa toda a fila",
        "leave": "Faz o bot sair do canal de voz",
        "volume": "Ajusta o volume (0-200)",
        "np": "Mostra a música atual",
        "shuffle": "Mistura a fila de músicas",
        "loop": "Configura repetição (off/song/queue)",
        "remove": "Remove uma música da fila",
        "search": "Busca músicas no YouTube"
    }
    
    for cmd, desc in commands_info.items():
        embed.add_field(
            name=f"{PREFIX}{cmd}",
            value=desc,
            inline=False
        )
    
    embed.add_field(
        name="🎵 Arquivos MP3",
        value="Anexe um arquivo .mp3 com `74!p` ou `74!playfile` para tocar!",
        inline=False
    )
    
    embed.set_footer(text="✨ Aceita links do YouTube, Spotify, SoundCloud, Deezer e arquivos MP3!")
    await ctx.send(embed=embed)

@bot.command(name='reload_commands')
@commands.is_owner()
async def reload_commands(ctx):
    """Recarrega os comandos (apenas dono do bot)"""
    try:
        await bot.reload_extension('music_cog')
        await ctx.send("✅ Comandos recarregados com sucesso!")
    except Exception as e:
        await ctx.send(f"❌ Erro ao recarregar: {str(e)}")

async def main():
    # Carregar a cog de música
    await bot.add_cog(MusicCog(bot))
    
    # Iniciar o bot
    try:
        await bot.start(TOKEN)
    except discord.LoginFailure:
        print("❌ Token inválido! Verifique seu arquivo .env")
    except Exception as e:
        print(f"❌ Erro ao iniciar bot: {str(e)}")

if __name__ == "__main__":
    asyncio.run(main())