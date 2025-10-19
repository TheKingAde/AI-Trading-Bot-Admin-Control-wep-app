from quart import Blueprint, jsonify

from utils.security import auth_required

performance_bp = Blueprint('performance', __name__)


@performance_bp.get('/performance')
@auth_required
async def get_performance(user):
    # Dummy performance per pair
    data = [
        {"pair": "EURUSD", "win_rate": 0.58, "drawdown": 0.12, "trades": 124},
        {"pair": "GBPUSD", "win_rate": 0.61, "drawdown": 0.09, "trades": 98},
        {"pair": "USDJPY", "win_rate": 0.55, "drawdown": 0.15, "trades": 85},
    ]
    return jsonify({"performance": data})
