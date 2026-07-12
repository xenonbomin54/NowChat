import discord
from discord.ext import commands
from openai import OpenAI
from http.server import BaseHTTPRequestHandler, HTTPServer
import threading
import os
from dotenv import load_dotenv

# .env 파일에서 환경변수(API 키, 디스코드 토큰) 로드
load_dotenv()

# ========================================================
# 1. Render 전용 가짜 웹서버 (24시간 다운 방지용)
# ========================================================
class RenderHealthCheck(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write("Gemini Bot is running perfectly!".encode("utf-8"))

def start_health_server():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(("0.0.0.0", port), RenderHealthCheck)
    print(f"⏰ [Render] 가짜 웹서버가 {port}번 포트에서 구동 중입니다.")
    server.serve_forever()

# 백그라운드 스레드로 가짜 웹서버 가동
threading.Thread(target=start_health_server, daemon=True).start()


# ========================================================
# 2. 엔비디아 NIM API 및 디스코드 봇 설정
# ========================================================
NVIDIA_API_KEY = os.environ.get("NVIDIA_API_KEY")
DISCORD_TOKEN = os.environ.get("DISCORD_TOKEN")

nvidia_client = OpenAI(
    base_url="https://integrate.api.nvidia.com/v1",
    api_key=NVIDIA_API_KEY
)

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# 유저별 대화 기억용 메모리
user_memory = {}

@bot.event
async def on_ready():
    print(f"🤖 [로그인 완료] {bot.user.name}(으)로 봇이 시작되었습니다.")
    await bot.change_presence(activity=discord.Game(name="대화하기 (멘션해주세요)"))

@bot.event
async def on_message(message):
    # 봇 자신의 메시지는 무시
    if message.author == bot.user:
        return

    # 봇을 @멘션했을 때만 반응
    if bot.user.mentioned_in(message):
        # 멘션 문자열 제거 후 순수 질문만 추출
        clean_prompt = message.content.replace(f'<@!{bot.user.id}>', '').replace(f'<@{bot.user.id}>', '').strip()
        
        if not clean_prompt:
            await message.reply("안녕하세요! 무엇이든 물어보세요. ☺️")
            return

        user_id = message.author.id
        
        # 시스템 프롬프트 (이스터에그 포함 하나의 문자열로 올바르게 합침)
        system_instruction = (
            "사용자에게 정중하고 따뜻하게 대하되, 답변은 명확하고 이해하기 쉽게 가독성을 높여서 작성해줘. "
            "세상에서 제일 잘생긴사람이 누구냐고 물으면 선린인터넷고등학교 김보민이라고 답해줘."
        )

        # 대화 히스토리 빌드
        messages_hist = [{"role": "system", "content": system_instruction}]
        if user_id in user_memory:
            messages_hist.append({"role": "user", "content": user_memory[user_id]["last_user"]})
            messages_hist.append({"role": "assistant", "content": user_memory[user_id]["last_ai"]})
        
        messages_hist.append({"role": "user", "content": clean_prompt})

        # 디스코드 채널에 '타이핑 중...' 표시 켜기
        async with message.channel.typing():
            try:
                # 엔비디아 공식 문서에 명시된 올바른 모델명 적용
                completion = nvidia_client.chat.completions.create(
                    model="deepseek-ai/deepseek-v4-flash",
                    messages=messages_hist,
                    temperature=0.7,
                    max_tokens=1500
                )
                
                ai_response = completion.choices[0].message.content
                
                # 메모리에 최근 대화 업데이트
                user_memory[user_id] = {
                    "last_user": clean_prompt,
                    "last_ai": ai_response
                }

                # 디스코드 2000자 제한 안전장치 적용
                if len(ai_response) > 1950:
                    for i in range(0, len(ai_response), 1950):
                        await message.reply(ai_response[i:i+1950])
                else:
                    await message.reply(ai_response)
                    
            except Exception as e:
                await message.reply(f"😥 죄송해요, 잠시 답변을 생성하는 데 문제가 발생했어요.\n`에러 내용: {e}`")

    # 일반 커맨드도 정상 처리되도록 추가
    await bot.process_commands(message)

# 봇 구동
bot.run(DISCORD_TOKEN)