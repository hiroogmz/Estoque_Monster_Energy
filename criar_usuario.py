"""Cria um usuário (ou troca a senha de um existente).  Uso:  py criar_usuario.py"""
import getpass

from werkzeug.security import generate_password_hash

from app import app, executar, init_db

init_db()
usuario = input("Nome do usuário: ").strip()
if not usuario or len(usuario) > 50:
    raise SystemExit("Nome inválido (1 a 50 caracteres).")

senha = getpass.getpass("Senha (mínimo 8 caracteres): ")
if len(senha) < 8:
    raise SystemExit("Senha muito curta.")
if senha != getpass.getpass("Repita a senha: "):
    raise SystemExit("As senhas não conferem.")

with app.app_context():
    executar(
        "INSERT INTO usuarios (usuario, senha_hash) VALUES (%s, %s) "
        "ON DUPLICATE KEY UPDATE senha_hash = VALUES(senha_hash)",
        (usuario, generate_password_hash(senha)),
    )
print(f"Usuário '{usuario}' salvo.")
