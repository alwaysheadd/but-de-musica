import discord
from discord.ext import commands
import yt_dlp as youtube_dl
import asyncio
import random
import os
import re
from collections import deque
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
from config import *

class MusicCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.voice_clients = {}
        self.queues = {}
        self.current_songs = {}
        self.loop_mode = {}  # 0: off, 1: song, 2: queue
        self.volume_levels = {}
        
        # Inicializar Spotify (opcional)
        if SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET:
            try:
                self.sp = spotipy.Spotify(auth_manager=SpotifyClientCredentials(
                    client_id=SPOTIFY_CLIENT_ID,
                    client_secret=SPOTIFY_CLIENT_SECRET
                ))
            except:
                self.sp = None
                print("Spotify não configurado corretamente")
        else:
            self.sp = None

    def get_command_aliases(self, command_name):
        """Retorna os aliases configurados para um comando"""
        return COMMANDS.get(command_name, [command_name])

    async def get_url_info(self, query, ctx):
        """Obtém informações da URL ou busca a música"""
        ytdl_opts = YTDL_OPTIONS.copy()
        
        with youtube_dl.YoutubeDL(ytdl_opts) as ydl:
            try:
                # Verificar se é URL do Spotify
                if 'open.spotify.com' in query and self.sp:
                    return await self.handle_spotify_url(query, ctx)
                
                # Verificar se é playlist
                if 'playlist' in query or 'list=' in query:
                    info = ydl.extract_info(query, download=False)
                    if 'entries' in info:
                        return {'type': 'playlist', 'entries': info['entries']}
                
                # Buscar vídeo único
                if not query.startswith(('http://', 'https://')):
                    query = f"ytsearch:{query}"
                
                info = ydl.extract_info(query, download=False)
                if 'entries' in info:
                    info = info['entries'][0]
                
                return {'type': 'single', 'info': info}
                
            except Exception as e:
                await ctx.send(f"❌ Erro ao buscar música: {str(e)}")
                return None

    async def handle_spotify_url(self, url, ctx):
        """Processa URLs do Spotify"""
        try:
            if 'track' in url:
                track_id = url.split('/')[-1].split('?')[0]
                track = self.sp.track(track_id)
                query = f"{track['name']} {track['artists'][0]['name']}"
                
            elif 'playlist' in url:
                playlist_id = url.split('/')[-1].split('?')[0]
                results = self.sp.playlist_tracks(playlist_id)
                tracks = []
                
                for item in results['items']:
                    track = item['track']
                    if track:
                        query = f"{track['name']} {track['artists'][0]['name']}"
                        tracks.append(query)
                
                return {'type': 'spotify_playlist', 'tracks': tracks}
                
            elif 'album' in url:
                album_id = url.split('/')[-1].split('?')[0]
                results = self.sp.album_tracks(album_id)
                tracks = []
                
                for track in results['items']:
                    query = f"{track['name']} {track['artists'][0]['name']}"
                    tracks.append(query)
                
                return {'type': 'spotify_album', 'tracks': tracks}
            
            if 'track' in url:
                with youtube_dl.YoutubeDL(YTDL_OPTIONS) as ydl:
                    info = ydl.extract_info(f"ytsearch:{query}", download=False)
                    if 'entries' in info:
                        info = info['entries'][0]
                    return {'type': 'single', 'info': info}
                    
        except Exception as e:
            await ctx.send(f"❌ Erro com Spotify: {str(e)}")
            return None

    async def play_next(self, ctx):
        """Toca a próxima música na fila"""
        guild_id = ctx.guild.id
        
        if guild_id in self.queues and self.queues[guild_id]:
            # Verificar modo loop
            if guild_id in self.loop_mode:
                if self.loop_mode[guild_id] == 1:  # Loop da música atual
                    if guild_id in self.current_songs:
                        song_info = self.current_songs[guild_id]
                        self.queues[guild_id].appendleft(song_info)
                elif self.loop_mode[guild_id] == 2:  # Loop da fila
                    if guild_id in self.current_songs:
                        song_info = self.current_songs[guild_id]
                        self.queues[guild_id].append(song_info)
            
            next_song = self.queues[guild_id].popleft()
            source_path = next_song['url']
            title = next_song.get('title', 'Desconhecido')
            
            self.current_songs[guild_id] = next_song
            
            voice_client = self.voice_clients.get(guild_id)
            if voice_client:
                try:
                    volume = self.volume_levels.get(guild_id, 0.5)
                    
                    # Verificar se é arquivo local ou URL
                    if source_path.startswith('local:'):
                        # Arquivo MP3 local
                        local_path = source_path.replace('local:', '')
                        source = await discord.FFmpegOpusAudio.from_probe(
                            local_path, **FFMPEG_OPTIONS
                        )
                    else:
                        # URL de streaming
                        source = await discord.FFmpegOpusAudio.from_probe(
                            source_path, **FFMPEG_OPTIONS
                        )
                    
                    source = discord.PCMVolumeTransformer(source, volume=volume)
                    
                    voice_client.play(source, after=lambda e: asyncio.run_coroutine_threadsafe(
                        self.play_next(ctx), self.bot.loop
                    ))
                    
                    embed = discord.Embed(
                        title="🎵 Tocando Agora",
                        description=f"**{title}**",
                        color=discord.Color.green()
                    )
                    await ctx.send(embed=embed)
                    
                except Exception as e:
                    await ctx.send(f"❌ Erro ao tocar música: {str(e)}")
                    await self.play_next(ctx)
        else:
            self.current_songs.pop(guild_id, None)
            self.loop_mode.pop(guild_id, None)

    @commands.command(name='play', aliases=COMMANDS['play'])
    async def play(self, ctx, *, query):
        """Toca música de várias plataformas ou links"""
        # Verificar se usuário está em canal de voz
        if not ctx.author.voice:
            await ctx.send("❌ Você precisa estar em um canal de voz!")
            return
        
        voice_channel = ctx.author.voice.channel
        
        # Conectar ao canal de voz
        if ctx.guild.id not in self.voice_clients:
            self.voice_clients[ctx.guild.id] = await voice_channel.connect()
            self.queues[ctx.guild.id] = deque()
            self.volume_levels[ctx.guild.id] = 0.5
        else:
            voice_client = self.voice_clients[ctx.guild.id]
            if voice_client.channel != voice_channel:
                await voice_client.move_to(voice_channel)
        
        # Verificar se é um anexo de arquivo
        if ctx.message.attachments:
            attachment = ctx.message.attachments[0]
            if attachment.filename.endswith(('.mp3', '.wav', '.ogg', '.m4a')):
                await self.handle_attachment(ctx, attachment)
                return
        
        # Processar query normal
        async with ctx.typing():
            result = await self.get_url_info(query, ctx)
            
            if not result:
                return
            
            if result['type'] == 'playlist':
                count = 0
                for entry in result['entries']:
                    song_info = {
                        'url': entry['url'],
                        'title': entry.get('title', 'Desconhecido'),
                        'duration': entry.get('duration', 0),
                        'requester': ctx.author.name
                    }
                    self.queues[ctx.guild.id].append(song_info)
                    count += 1
                
                embed = discord.Embed(
                    title="📋 Playlist Adicionada",
                    description=f"**{count} músicas** adicionadas à fila!",
                    color=discord.Color.blue()
                )
                await ctx.send(embed=embed)
                
            elif result['type'] in ['spotify_playlist', 'spotify_album']:
                count = 0
                for track_query in result['tracks']:
                    track_result = await self.get_url_info(track_query, ctx)
                    if track_result and track_result['type'] == 'single':
                        song_info = {
                            'url': track_result['info']['url'],
                            'title': track_result['info'].get('title', 'Desconhecido'),
                            'duration': track_result['info'].get('duration', 0),
                            'requester': ctx.author.name
                        }
                        self.queues[ctx.guild.id].append(song_info)
                        count += 1
                
                embed = discord.Embed(
                    title="📋 Playlist do Spotify Adicionada",
                    description=f"**{count} músicas** adicionadas à fila!",
                    color=discord.Color.green()
                )
                await ctx.send(embed=embed)
                
            elif result['type'] == 'single':
                song_info = {
                    'url': result['info']['url'],
                    'title': result['info'].get('title', 'Desconhecido'),
                    'duration': result['info'].get('duration', 0),
                    'requester': ctx.author.name
                }
                self.queues[ctx.guild.id].append(song_info)
                
                embed = discord.Embed(
                    title="✅ Música Adicionada",
                    description=f"**{song_info['title']}**",
                    color=discord.Color.green()
                )
                await ctx.send(embed=embed)
        
        # Se não estiver tocando, iniciar reprodução
        voice_client = self.voice_clients[ctx.guild.id]
        if not voice_client.is_playing():
            await self.play_next(ctx)

    async def handle_attachment(self, ctx, attachment):
        """Processa arquivos de áudio anexados"""
        try:
            # Criar pasta se não existir
            os.makedirs(MUSIC_FOLDER, exist_ok=True)
            
            # Baixar arquivo
            file_path = os.path.join(MUSIC_FOLDER, attachment.filename)
            await attachment.save(file_path)
            
            song_info = {
                'url': f'local:{file_path}',
                'title': attachment.filename,
                'duration': 0,
                'requester': ctx.author.name
            }
            
            self.queues[ctx.guild.id].append(song_info)
            
            embed = discord.Embed(
                title="✅ Arquivo MP3 Adicionado",
                description=f"**{attachment.filename}**",
                color=discord.Color.green()
            )
            await ctx.send(embed=embed)
            
            # Se não estiver tocando, iniciar reprodução
            voice_client = self.voice_clients[ctx.guild.id]
            if not voice_client.is_playing():
                await self.play_next(ctx)
                
        except Exception as e:
            await ctx.send(f"❌ Erro ao processar arquivo: {str(e)}")

    @commands.command(name='playfile', aliases=COMMANDS['playfile'])
    async def playfile(self, ctx):
        """Toca um arquivo MP3 anexado"""
        if not ctx.message.attachments:
            await ctx.send("❌ Você precisa anexar um arquivo de áudio!")
            return
        
        attachment = ctx.message.attachments[0]
        if not attachment.filename.endswith(('.mp3', '.wav', '.ogg', '.m4a')):
            await ctx.send("❌ Formato não suportado! Use MP3, WAV, OGG ou M4A")
            return
        
        await self.play(ctx, query="")  # Chama o play que vai detectar o anexo

    @commands.command(name='stop', aliases=COMMANDS['stop'])
    async def stop(self, ctx):
        """Para a música e limpa a fila"""
        guild_id = ctx.guild.id
        
        if guild_id in self.voice_clients:
            voice_client = self.voice_clients[guild_id]
            if voice_client.is_playing():
                voice_client.stop()
            
            self.queues[guild_id].clear()
            await ctx.send("⏹️ Música parada e fila limpa!")

    @commands.command(name='pause', aliases=COMMANDS['pause'])
    async def pause(self, ctx):
        """Pausa a música atual"""
        guild_id = ctx.guild.id
        
        if guild_id in self.voice_clients:
            voice_client = self.voice_clients[guild_id]
            if voice_client.is_playing():
                voice_client.pause()
                await ctx.send("⏸️ Música pausada!")

    @commands.command(name='resume', aliases=COMMANDS['resume'])
    async def resume(self, ctx):
        """Continua a música pausada"""
        guild_id = ctx.guild.id
        
        if guild_id in self.voice_clients:
            voice_client = self.voice_clients[guild_id]
            if voice_client.is_paused():
                voice_client.resume()
                await ctx.send("▶️ Música continuando!")

    @commands.command(name='skip', aliases=COMMANDS['skip'])
    async def skip(self, ctx):
        """Pula para a próxima música"""
        guild_id = ctx.guild.id
        
        if guild_id in self.voice_clients:
            voice_client = self.voice_clients[guild_id]
            if voice_client.is_playing():
                voice_client.stop()
                await ctx.send("⏭️ Música pulada!")
            else:
                await ctx.send("❌ Não há música tocando!")

    @commands.command(name='queue', aliases=COMMANDS['queue'])
    async def queue(self, ctx, page: int = 1):
        """Mostra a fila de músicas"""
        guild_id = ctx.guild.id
        
        if guild_id not in self.queues or not self.queues[guild_id]:
            await ctx.send("📭 A fila está vazia!")
            return
        
        queue_list = list(self.queues[guild_id])
        items_per_page = 10
        pages = (len(queue_list) + items_per_page - 1) // items_per_page
        
        if page < 1 or page > pages:
            await ctx.send(f"❌ Página inválida! Use páginas de 1 a {pages}")
            return
        
        start = (page - 1) * items_per_page
        end = min(start + items_per_page, len(queue_list))
        
        embed = discord.Embed(
            title="📋 Fila de Músicas",
            color=discord.Color.blue()
        )
        
        for i in range(start, end):
            song = queue_list[i]
            duration = song.get('duration', 0)
            duration_str = f"{duration // 60}:{duration % 60:02d}" if duration else "??:??"
            
            embed.add_field(
                name=f"{i + 1}. {song['title'][:50]}",
                value=f"Duração: {duration_str} | Solicitado por: {song['requester']}",
                inline=False
            )
        
        embed.set_footer(text=f"Página {page}/{pages} • Total: {len(queue_list)} músicas")
        await ctx.send(embed=embed)

    @commands.command(name='clear', aliases=COMMANDS['clear'])
    async def clear(self, ctx):
        """Limpa a fila de músicas"""
        guild_id = ctx.guild.id
        
        if guild_id in self.queues:
            self.queues[guild_id].clear()
            await ctx.send("🧹 Fila limpa!")

    @commands.command(name='leave', aliases=COMMANDS['leave'])
    async def leave(self, ctx):
        """Faz o bot sair do canal de voz"""
        guild_id = ctx.guild.id
        
        if guild_id in self.voice_clients:
            voice_client = self.voice_clients[guild_id]
            
            if guild_id in self.queues:
                self.queues[guild_id].clear()
            
            await voice_client.disconnect()
            
            self.voice_clients.pop(guild_id, None)
            self.queues.pop(guild_id, None)
            self.current_songs.pop(guild_id, None)
            self.loop_mode.pop(guild_id, None)
            
            await ctx.send("👋 Saindo do canal!")

    @commands.command(name='volume', aliases=COMMANDS['volume'])
    async def volume(self, ctx, volume: int = None):
        """Ajusta o volume da música (0-200)"""
        guild_id = ctx.guild.id
        
        if volume is None:
            current_volume = int(self.volume_levels.get(guild_id, 0.5) * 100)
            await ctx.send(f"🔊 Volume atual: **{current_volume}%**")
            return
        
        if 0 <= volume <= 200:
            volume_level = volume / 100
            self.volume_levels[guild_id] = volume_level
            
            if guild_id in self.voice_clients:
                voice_client = self.voice_clients[guild_id]
                if voice_client.source:
                    voice_client.source.volume = volume_level
            
            await ctx.send(f"🔊 Volume ajustado para **{volume}%**")
        else:
            await ctx.send("❌ Volume deve estar entre 0 e 200!")

    @commands.command(name='nowplaying', aliases=COMMANDS['nowplaying'])
    async def nowplaying(self, ctx):
        """Mostra a música que está tocando agora"""
        guild_id = ctx.guild.id
        
        if guild_id in self.current_songs:
            song = self.current_songs[guild_id]
            
            voice_client = self.voice_clients.get(guild_id)
            is_playing = voice_client and voice_client.is_playing()
            
            embed = discord.Embed(
                title="🎵 Tocando Agora" if is_playing else "⏸️ Pausado",
                description=f"**{song['title']}**",
                color=discord.Color.green() if is_playing else discord.Color.orange()
            )
            
            duration = song.get('duration', 0)
            duration_str = f"{duration // 60}:{duration % 60:02d}" if duration else "??:??"
            
            embed.add_field(name="Duração", value=duration_str)
            embed.add_field(name="Solicitado por", value=song['requester'])
            
            await ctx.send(embed=embed)
        else:
            await ctx.send("❌ Nenhuma música tocando no momento!")

    @commands.command(name='shuffle', aliases=COMMANDS['shuffle'])
    async def shuffle(self, ctx):
        """Mistura a fila de músicas"""
        guild_id = ctx.guild.id
        
        if guild_id in self.queues and self.queues[guild_id]:
            queue_list = list(self.queues[guild_id])
            random.shuffle(queue_list)
            self.queues[guild_id] = deque(queue_list)
            await ctx.send("🔀 Fila misturada!")
        else:
            await ctx.send("❌ A fila está vazia!")

    @commands.command(name='loop', aliases=COMMANDS['loop'])
    async def loop(self, ctx, mode: str = None):
        """Configura o modo de repetição (off/song/queue)"""
        guild_id = ctx.guild.id
        
        loop_modes = {
            'off': 0,
            'song': 1,
            'queue': 2,
            '0': 0,
            '1': 1,
            '2': 2
        }
        
        if mode is None:
            current_mode = self.loop_mode.get(guild_id, 0)
            mode_names = {0: 'Desligado', 1: 'Música', 2: 'Fila'}
            await ctx.send(f"🔁 Modo loop atual: **{mode_names[current_mode]}**")
            await ctx.send("Use: `74!loop off/song/queue`")
            return
        
        mode = mode.lower()
        if mode in loop_modes:
            self.loop_mode[guild_id] = loop_modes[mode]
            mode_names = {0: 'Desligado', 1: 'Música', 2: 'Fila'}
            await ctx.send(f"🔁 Modo loop alterado para: **{mode_names[loop_modes[mode]]}**")
        else:
            await ctx.send("❌ Modo inválido! Use: `off`, `song` ou `queue`")

    @commands.command(name='remove', aliases=COMMANDS['remove'])
    async def remove(self, ctx, index: int):
        """Remove uma música específica da fila"""
        guild_id = ctx.guild.id
        
        if guild_id not in self.queues or not self.queues[guild_id]:
            await ctx.send("❌ A fila está vazia!")
            return
        
        if 1 <= index <= len(self.queues[guild_id]):
            queue_list = list(self.queues[guild_id])
            removed_song = queue_list.pop(index - 1)
            self.queues[guild_id] = deque(queue_list)
            
            # Se for arquivo local, deletar
            if removed_song['url'].startswith('local:'):
                try:
                    file_path = removed_song['url'].replace('local:', '')
                    if os.path.exists(file_path):
                        os.remove(file_path)
                except:
                    pass
            
            await ctx.send(f"🗑️ Removido: **{removed_song['title']}**")
        else:
            await ctx.send(f"❌ Índice inválido! Use números de 1 a {len(self.queues[guild_id])}")

    @commands.command(name='search', aliases=COMMANDS['search'])
    async def search(self, ctx, *, query):
        """Busca músicas e mostra resultados"""
        async with ctx.typing():
            ytdl_opts = YTDL_OPTIONS.copy()
            ytdl_opts['extract_flat'] = True
            
            with youtube_dl.YoutubeDL(ytdl_opts) as ydl:
                try:
                    info = ydl.extract_info(f"ytsearch5:{query}", download=False)
                    
                    if 'entries' not in info:
                        await ctx.send("❌ Nenhum resultado encontrado!")
                        return
                    
                    embed = discord.Embed(
                        title=f"🔍 Resultados para: {query[:50]}",
                        color=discord.Color.blue()
                    )
                    
                    results = []
                    for i, entry in enumerate(info['entries'][:5], 1):
                        title = entry.get('title', 'Desconhecido')
                        duration = entry.get('duration', 0)
                        duration_str = f"{duration // 60}:{duration % 60:02d}" if duration else "??:??"
                        
                        embed.add_field(
                            name=f"{i}. {title[:50]}",
                            value=f"Duração: {duration_str}",
                            inline=False
                        )
                        results.append(entry)
                    
                    embed.set_footer(text="Use 74!p [número] para tocar")
                    await ctx.send(embed=embed)
                    
                    # Armazenar resultados para seleção
                    self.bot.search_results[ctx.author.id] = results
                    
                except Exception as e:
                    await ctx.send(f"❌ Erro na busca: {str(e)}")

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        """Sai do canal se ficar sozinho"""
        if member == self.bot.user:
            return
        
        voice_clients = [vc for vc in self.voice_clients.values() if vc.channel == before.channel]
        
        if voice_clients and before.channel:
            if len(before.channel.members) == 1:  # Apenas o bot
                for guild_id, vc in list(self.voice_clients.items()):
                    if vc.channel == before.channel:
                        await vc.disconnect()
                        self.voice_clients.pop(guild_id, None)
                        self.queues.pop(guild_id, None)
                        self.current_songs.pop(guild_id, None)
                        self.loop_mode.pop(guild_id, None)

def setup(bot):
    bot.add_cog(MusicCog(bot))