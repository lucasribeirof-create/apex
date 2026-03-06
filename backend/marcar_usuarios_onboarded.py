"""
Script único: marca todos os usuários existentes como onboarding completo.
Assim eles passam a aparecer na tela "Selecionar carteira" em vez de "Iniciar Diagnóstico".

Uso: cd backend && python marcar_usuarios_onboarded.py
"""
import sys
sys.path.insert(0, ".")

from app.models.base import SessionLocal
from app.models import User

def main():
    db = SessionLocal()
    try:
        users = db.query(User).all()
        if not users:
            print("Nenhum usuario no banco. Crie um pelo onboarding no app.")
            return
        for u in users:
            if not u.onboarding_completo:
                u.onboarding_completo = True
                print(f"  [OK] Usuario id={u.id} nome={u.name!r} -> onboarding_completo=True")
        db.commit()
        print(f"Pronto. {len(users)} usuario(s) agora aparecem em 'Selecionar carteira'.")
    finally:
        db.close()

if __name__ == "__main__":
    main()
