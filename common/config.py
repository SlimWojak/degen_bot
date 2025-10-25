# config.py
from dataclasses import dataclass
from typing import Literal
import os, sys
from dotenv import load_dotenv

load_dotenv()  # local runs; Docker will pass envs directly

Env = Literal["mainnet", "testnet"]

@dataclass(frozen=True)
class HLConfig:
    env: Env
    account: str           # master funded address
    api_wallet: str        # API wallet public address
    private_key: str
    rest_url: str
    ws_url: str

@dataclass(frozen=True)
class DSConfig:
    api_key: str
    model: str

@dataclass(frozen=True)
class BotConfig:
    assets: list[str]
    start_capital: float
    min_score: float
    max_leverage: float
    daily_dd_limit: float
    position_risk: float
    db_path: str

@dataclass(frozen=True)
class AppConfig:
    hl: HLConfig
    ds: DSConfig
    bot: BotConfig

def _require(name: str) -> str:
    v = os.getenv(name)
    if not v:
        print(f"[CONFIG] Missing env var: {name}", file=sys.stderr)
        raise SystemExit(2)
    return v

def load_config() -> AppConfig:
    env = os.getenv("HL_ENV", "testnet").lower()
    if env not in ("mainnet", "testnet"):
        raise SystemExit("[CONFIG] HL_ENV must be 'mainnet' or 'testnet'")

    rest = os.getenv("HL_REST_MAIN") if env == "mainnet" else os.getenv("HL_REST_TEST")
    ws   = os.getenv("HL_WS_MAIN")   if env == "mainnet" else os.getenv("HL_WS_TEST")
    if not rest or not ws:
        raise SystemExit("[CONFIG] Missing HL endpoints for selected HL_ENV")

    assets = [a.strip().upper() for a in _require("ASSETS").split(",") if a.strip()]

    return AppConfig(
        hl=HLConfig(
            env=env,
            account=_require("HL_ACCOUNT_ADDRESS"),
            api_wallet=_require("HL_API_WALLET_ADDRESS"),
            private_key=_require("HL_PRIVATE_KEY"),
            rest_url=rest,
            ws_url=ws,
        ),
        ds=DSConfig(
            api_key=_require("DEEPSEEK_API_KEY"),
            model=os.getenv("DEEPSEEK_MODEL", "deepseek-chat"),
        ),
        bot=BotConfig(
            assets=assets,
            start_capital=float(os.getenv("START_CAPITAL", "10000")),
            min_score=float(os.getenv("MIN_SCORE", "80")),
            max_leverage=float(os.getenv("MAX_LEVERAGE", "5")),
            daily_dd_limit=float(os.getenv("DAILY_DRAWDOWN_LIMIT", "0.10")),
            position_risk=float(os.getenv("POSITION_RISK", "0.02")),
            db_path=os.getenv("DB_PATH", "./data/degen.sqlite"),
        ),
    )

def redacted(cfg: AppConfig) -> dict:
    return {
        "hl": {
            "env": cfg.hl.env,
            "account": cfg.hl.account[:6] + "..." + cfg.hl.account[-4:],
            "api_wallet": cfg.hl.api_wallet[:6] + "..." + cfg.hl.api_wallet[-4:],
            "rest_url": cfg.hl.rest_url,
            "ws_url": cfg.hl.ws_url,
        },
        "ds": {"model": cfg.ds.model, "api_key": "sk-***redacted***"},
        "bot": {
            "assets": cfg.bot.assets,
            "start_capital": cfg.bot.start_capital,
            "min_score": cfg.bot.min_score,
            "max_leverage": cfg.bot.max_leverage,
            "daily_dd_limit": cfg.bot.daily_dd_limit,
            "position_risk": cfg.bot.position_risk,
            "db_path": cfg.bot.db_path,
        },
    }
