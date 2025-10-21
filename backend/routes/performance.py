from quart import Blueprint, jsonify

from utils.security import auth_required

performance_bp = Blueprint('performance', __name__)


@performance_bp.get('/performance')
@auth_required
async def get_performance(user):
    # Dummy performance per pair
    data = [
        {"pair": "unavailable", "win_rate": 0, "drawdown": 0, "trades": 0},
        {"pair": "unavailable", "win_rate": 0, "drawdown": 0, "trades": 0},
        {"pair": "unavailable", "win_rate": 0, "drawdown": 0, "trades": 0},
    ]
    return jsonify({"performance": data})
