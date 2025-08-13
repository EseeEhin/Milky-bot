module.exports = {
  apps : [{
    name: "milky-bot",
    script: "bot.py",
    interpreter: "python",
    env: {
      "PYTHONIOENCODING": "UTF-8"
    }
  }]
}
