# 使用更具体且轻量的基础镜像
FROM python:3.11.4-slim

# 设置工作目录
WORKDIR /app

# 创建一个非root用户来运行应用，增强安全性
RUN useradd -m -u 1000 appuser
USER appuser

# 将当前目录内容复制到容器的/app目录下
# 使用chown确保appuser拥有这些文件的权限
COPY --chown=appuser:appuser . .

# 安装依赖
RUN pip install --no-cache-dir -r requirements.txt

# 声明应用将监听的端口（用于健康检查）
EXPOSE 7860

# 设置PYTHONUNBUFFERED可以确保日志直接输出，方便在HF Spaces中查看
ENV PYTHONUNBUFFERED=1

# 运行bot
CMD ["python", "bot.py"] 