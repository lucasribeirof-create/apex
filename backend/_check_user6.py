"""Quick check: verify what the running backend sees for user 6."""
import sys
sys.path.insert(0, ".")
from app.models import SessionLocal, Portfolio
from app.models.user import User

db = SessionLocal()
u6 = db.query(User).filter(User.id == 6).first()
if u6:
    print(f"User 6: {u6.name}, estrategia={u6.estrategia}, portfolio_ativo_id={u6.portfolio_ativo_id}")
    p = db.query(Portfolio).filter(Portfolio.user_id == 6).first()
    if p:
        print(f"Portfolio: id={p.id}, patrimonio={p.patrimonio_total}, nome={p.nome}")
    else:
        print("NO portfolio for user 6!")
    all_p = db.query(Portfolio).all()
    print(f"Total portfolios in DB: {len(all_p)}")
    for p in all_p:
        print(f"  id={p.id} user_id={p.user_id} patrimonio={p.patrimonio_total}")
else:
    print("User 6 not found!")
    all_users = db.query(User).all()
    print(f"Total users: {len(all_users)}")
    for u in all_users:
        print(f"  id={u.id} name={u.name}")
db.close()
