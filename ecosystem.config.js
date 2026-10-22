module.exports = {
  apps: [{
    name: "gonkafarm-20",
    script: "farm.py",
    cwd: "/home/gowangz/PROJECT/GITHUB/GONKAFARM",
    interpreter: "python3",
    args: "--accounts 20 --workers 1",
    autorestart: false,
    max_memory_restart: "512M",
    out_file: "logs/pm2-out.log",
    error_file: "logs/pm2-err.log",
    merge_logs: true,
    time: true
  }]
};
