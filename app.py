"""
Estoque de uma bebida só (Monster Energy) com MySQL e login.

1) py -m pip install -r requirements.txt
2) copie .env.example para .env e ajuste a senha do banco
3) py app.py
Computador: http://127.0.0.1:5000      Celular: /celular (ou QR code em /qr)
"""
import os
import re
import secrets
import socket
from datetime import timedelta
from io import BytesIO
from urllib.parse import urlparse

import pymysql
import pymysql.cursors
import qrcode
import qrcode.image.svg
from dotenv import load_dotenv
from flask import (Flask, Response, flash, g, redirect, render_template,
                   request, session, url_for)
from flask_wtf.csrf import CSRFError, CSRFProtect
from werkzeug.security import check_password_hash, generate_password_hash

load_dotenv()

# ---- Configurações da bebida (troque aqui) ---------------------------------
BEBIDA = "Monster Energy"
EMBALAGEM = "Lata 473 ml"
PRECO_UNIDADE = 9.99
ESTOQUE_MINIMO = 6
UNIDADES_POR_CAIXA = 6
PORTA = 5000
URL_BASE = ""      # opcional: endereço fixo para o QR code (ex.: IP da VM)

# ---- Banco de dados (vem do arquivo .env) ----------------------------------
DB_HOST = os.environ.get("DB_HOST", "127.0.0.1")
DB_PORT = int(os.environ.get("DB_PORT", "3306"))
DB_USER = os.environ.get("DB_USER", "estoque")
DB_SENHA = os.environ.get("DB_SENHA", "")
DB_NOME = os.environ.get("DB_NOME", "estoque")

# ---- Segurança -------------------------------------------------------------
MAX_TENTATIVAS_IP = 5          # falhas por IP dentro da janela
MAX_TENTATIVAS_USUARIO = 10    # falhas por nome de usuário dentro da janela
JANELA_BLOQUEIO_MIN = 15       # minutos
SESSAO_MINUTOS = 30            # sessão expira após esse tempo
COOKIE_SEGURO = os.environ.get("COOKIE_SEGURO", "0") == "1"
DEBUG = os.environ.get("DEBUG", "0") == "1"
# ----------------------------------------------------------------------------

if not re.fullmatch(r"[A-Za-z0-9_]+", DB_NOME):
    raise SystemExit("DB_NOME inválido: use só letras, números e _")

SECRET_KEY = os.environ.get("SECRET_KEY")
if not SECRET_KEY:
    SECRET_KEY = secrets.token_hex(32)
    print("AVISO: SECRET_KEY não definida no .env. Usando uma chave temporária "
          "(os logins são perdidos a cada reinício).")

app = Flask(__name__)
app.config.update(
    SECRET_KEY=SECRET_KEY,
    SESSION_COOKIE_HTTPONLY=True,       # JavaScript não lê o cookie
    SESSION_COOKIE_SAMESITE="Lax",      # reduz CSRF vindo de outros sites
    SESSION_COOKIE_SECURE=COOKIE_SEGURO,
    PERMANENT_SESSION_LIFETIME=timedelta(minutes=SESSAO_MINUTOS),
    MAX_CONTENT_LENGTH=100_000,         # rejeita corpos de requisição grandes
    WTF_CSRF_TIME_LIMIT=None,           # token vale enquanto a sessão valer
)
CSRFProtect(app)

# Hash usado quando o usuário não existe, para o tempo de resposta não revelar
# quais nomes de usuário são válidos.
SENHA_FALSA = generate_password_hash(secrets.token_hex(8))


# ============================ banco de dados ================================
def conectar(com_banco=True):
    return pymysql.connect(
        host=DB_HOST, port=DB_PORT, user=DB_USER, password=DB_SENHA,
        database=DB_NOME if com_banco else None,
        charset="utf8mb4", cursorclass=pymysql.cursors.DictCursor,
        autocommit=False, connect_timeout=5,
    )


def get_db():
    if "db" not in g:
        g.db = conectar()
    return g.db


@app.teardown_appcontext
def fechar_db(_):
    db = g.pop("db", None)
    if db:
        db.close()


def consultar(sql, params=(), um=False):
    """SELECT sempre com parâmetros (%s): evita SQL injection."""
    with get_db().cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchone() if um else cur.fetchall()


def executar(sql, params=()):
    db = get_db()
    with db.cursor() as cur:
        cur.execute(sql, params)
    db.commit()


TABELAS = [
    """CREATE TABLE IF NOT EXISTS usuarios (
        id INT AUTO_INCREMENT PRIMARY KEY,
        usuario VARCHAR(50) NOT NULL UNIQUE,
        senha_hash VARCHAR(255) NOT NULL,
        criado_em DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
    """CREATE TABLE IF NOT EXISTS movimentos (
        id INT AUTO_INCREMENT PRIMARY KEY,
        tipo ENUM('entrada','saida') NOT NULL,
        quantidade INT NOT NULL,
        sabor VARCHAR(120),
        usuario VARCHAR(50) NOT NULL,
        criado_em DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        INDEX idx_usuario (usuario),
        CONSTRAINT chk_quantidade CHECK (quantidade > 0)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
    """CREATE TABLE IF NOT EXISTS tentativas_login (
        id INT AUTO_INCREMENT PRIMARY KEY,
        usuario VARCHAR(50) NOT NULL,
        ip VARCHAR(45) NOT NULL,
        criado_em DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        INDEX idx_ip (ip, criado_em),
        INDEX idx_usuario (usuario, criado_em)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
    """CREATE TABLE IF NOT EXISTS contribuintes (
        id INT AUTO_INCREMENT PRIMARY KEY,
        dono VARCHAR(50) NOT NULL,
        contribuinte VARCHAR(50) NOT NULL UNIQUE,
        criado_em DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        INDEX idx_dono (dono),
        INDEX idx_contribuinte (contribuinte)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
]


def init_db():
    """Cria o banco, as tabelas e o primeiro usuário, se ainda não existirem."""
    try:
        con = conectar(com_banco=False)
        with con.cursor() as cur:
            cur.execute(
                f"CREATE DATABASE IF NOT EXISTS `{DB_NOME}` "
                "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            )
        con.commit()
        con.close()
    except pymysql.err.OperationalError as erro:
        print(f"Aviso: não consegui criar o banco ({erro.args[-1]}). "
              "Seguindo, caso ele já exista.")

    with app.app_context():
        for sql in TABELAS:
            executar(sql)
        try:
            executar("UPDATE movimentos SET usuario = 'admin' WHERE usuario IS NULL")
        except Exception:
            pass
        try:
            idx = consultar("SHOW INDEX FROM movimentos WHERE Key_name = 'idx_usuario'", um=True)
            if not idx:
                executar("CREATE INDEX idx_usuario ON movimentos (usuario)")
        except Exception:
            pass
        garantir_admin()


def garantir_admin():
    if consultar("SELECT COUNT(*) AS n FROM usuarios", um=True)["n"]:
        return
    nome = os.environ.get("ADMIN_USUARIO", "admin").strip() or "admin"
    senha = os.environ.get("ADMIN_SENHA", "")
    gerada = not senha
    if gerada:
        senha = secrets.token_urlsafe(12)
    executar("INSERT INTO usuarios (usuario, senha_hash) VALUES (%s, %s)",
             (nome, generate_password_hash(senha)))
    print("=" * 56)
    print(f"Primeiro usuário criado: {nome}")
    if gerada:
        print(f"Senha gerada (anote agora, ela não aparece de novo): {senha}")
    print("=" * 56)


# ============================ regras do estoque =============================
def conta_estoque_atual():
    """Retorna o dono do estoque da sessão atual (se for contribuinte, retorna o dono)."""
    return session.get("conta_estoque") or session.get("dono") or session.get("usuario")


def estoque_atual(conta=None):
    if conta is None:
        conta = conta_estoque_atual()
    if not conta:
        return 0
    row = consultar(
        """SELECT COALESCE(SUM(CASE tipo WHEN 'entrada' THEN quantidade
                                         ELSE -quantidade END), 0) AS total
           FROM movimentos
           WHERE (usuario = %s OR usuario IN (SELECT contribuinte FROM contribuintes WHERE dono = %s))""",
        (conta, conta),
        um=True,
    )
    return int(row["total"])


def registrar(tipo, qtd, sabor, usuario=None):
    if usuario is None:
        usuario = session.get("usuario")
    executar(
        "INSERT INTO movimentos (tipo, quantidade, sabor, usuario) "
        "VALUES (%s, %s, %s, %s)",
        (tipo, qtd, (sabor or "")[:120] or None, usuario),
    )


def texto_movimento(tipo, qtd):
    nome = "Entrada" if tipo == "entrada" else "Saída"
    return f"{nome} de {qtd} unidade{'s' if qtd != 1 else ''} registrada."


def ler_quantidade(valor):
    try:
        qtd = int(valor)
    except (TypeError, ValueError):
        return 0
    return qtd if 0 < qtd <= 10000 else 0


# ============================ login e proteção ==============================
def destino_seguro(alvo):
    """Só aceita caminhos internos (evita redirecionar para outro site)."""
    if alvo and alvo.startswith("/") and not alvo.startswith("//") \
            and "\\" not in alvo and not urlparse(alvo).netloc:
        return alvo
    return url_for("index")


def esta_bloqueado(usuario, ip):
    r = consultar(
        """SELECT SUM(ip = %s) AS por_ip, SUM(usuario = %s) AS por_usuario
           FROM tentativas_login
           WHERE criado_em > NOW() - INTERVAL %s MINUTE""",
        (ip, usuario, JANELA_BLOQUEIO_MIN), um=True,
    )
    return (int(r["por_ip"] or 0) >= MAX_TENTATIVAS_IP
            or int(r["por_usuario"] or 0) >= MAX_TENTATIVAS_USUARIO)


@app.before_request
def exigir_login():
    if request.endpoint in (None, "login", "cadastro", "static"):
        return None
    if "usuario" not in session:
        proximo = request.path if request.method == "GET" else None
        return redirect(url_for("login", next=proximo))
    return None


@app.after_request
def cabecalhos_de_seguranca(resp):
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["X-Frame-Options"] = "DENY"
    resp.headers["Referrer-Policy"] = "same-origin"
    resp.headers["Content-Security-Policy"] = (
        "default-src 'self'; script-src 'self'; "
        "style-src 'self' https://fonts.googleapis.com; "
        "font-src https://fonts.gstatic.com; img-src 'self' data:; "
        "form-action 'self'; frame-ancestors 'none'; base-uri 'self'"
    )
    if request.endpoint != "static":
        resp.headers["Cache-Control"] = "no-store"
    return resp


@app.errorhandler(CSRFError)
def erro_csrf(_):
    flash("A página expirou. Tente novamente.", "erro")
    return redirect(url_for("login" if "usuario" not in session else "index"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if "usuario" in session:
        return redirect(url_for("index"))

    if request.method == "POST":
        usuario = request.form.get("usuario", "").strip()[:50]
        senha = request.form.get("senha", "")[:128]
        ip = request.remote_addr or "desconhecido"

        if esta_bloqueado(usuario, ip):
            flash(f"Muitas tentativas. Aguarde {JANELA_BLOQUEIO_MIN} minutos.", "erro")
            return render_template("login.html", bebida=BEBIDA), 429

        row = consultar(
            "SELECT usuario, senha_hash FROM usuarios WHERE usuario = %s",
            (usuario,), um=True,
        )
        senha_ok = check_password_hash(row["senha_hash"] if row else SENHA_FALSA, senha)

        if row and senha_ok:
            executar("DELETE FROM tentativas_login WHERE usuario = %s AND ip = %s",
                     (usuario, ip))
            contrib = consultar(
                "SELECT dono FROM contribuintes WHERE contribuinte = %s",
                (row["usuario"],), um=True,
            )
            dono = contrib["dono"] if contrib else None

            session.clear()                      # evita fixação de sessão
            session["usuario"] = row["usuario"]
            session["dono"] = dono
            session["conta_estoque"] = dono if dono else row["usuario"]
            session.permanent = True
            return redirect(destino_seguro(request.args.get("next")))

        executar("INSERT INTO tentativas_login (usuario, ip) VALUES (%s, %s)",
                 (usuario, ip))
        flash("Usuário ou senha inválidos.", "erro")   # mesma mensagem nos dois casos
        return render_template("login.html", bebida=BEBIDA), 401

    return render_template("login.html", bebida=BEBIDA)


@app.route("/cadastro", methods=["GET", "POST"])
def cadastro():
    if "usuario" in session:
        return redirect(url_for("index"))

    if request.method == "POST":
        usuario = request.form.get("usuario", "").strip()
        senha = request.form.get("senha", "")
        confirmar_senha = request.form.get("confirmar_senha", "")

        if not usuario or len(usuario) < 3 or len(usuario) > 50:
            flash("O nome de usuário deve ter entre 3 e 50 caracteres.", "erro")
            return render_template("cadastro.html", bebida=BEBIDA, usuario=usuario), 400

        if not re.fullmatch(r"[A-Za-z0-9_.-]+", usuario):
            flash("O usuário deve conter apenas letras, números, sublinhado (_), hífen (-) e ponto (.).", "erro")
            return render_template("cadastro.html", bebida=BEBIDA, usuario=usuario), 400

        if len(senha) < 6:
            flash("A senha deve ter no mínimo 6 caracteres.", "erro")
            return render_template("cadastro.html", bebida=BEBIDA, usuario=usuario), 400

        if len(senha) > 128:
            flash("A senha não pode ter mais de 128 caracteres.", "erro")
            return render_template("cadastro.html", bebida=BEBIDA, usuario=usuario), 400

        if senha != confirmar_senha:
            flash("As senhas informadas não conferem.", "erro")
            return render_template("cadastro.html", bebida=BEBIDA, usuario=usuario), 400

        existente = consultar("SELECT id FROM usuarios WHERE usuario = %s", (usuario,), um=True)
        if existente:
            flash("Este nome de usuário já está em uso.", "erro")
            return render_template("cadastro.html", bebida=BEBIDA, usuario=usuario), 400

        senha_hash = generate_password_hash(senha)
        try:
            executar("INSERT INTO usuarios (usuario, senha_hash) VALUES (%s, %s)",
                     (usuario, senha_hash))
        except pymysql.err.IntegrityError:
            flash("Este nome de usuário já está em uso.", "erro")
            return render_template("cadastro.html", bebida=BEBIDA, usuario=usuario), 400

        flash("Cadastro realizado com sucesso! Faça login para continuar.", "ok")
        return redirect(url_for("login"))

    return render_template("cadastro.html", bebida=BEBIDA)


@app.route("/trocar-senha", methods=["GET", "POST"])
def trocar_senha():
    if request.method == "POST":
        senha_atual = request.form.get("senha_atual", "")
        nova_senha = request.form.get("nova_senha", "")
        confirmar_nova = request.form.get("confirmar_nova", "")

        usuario = session.get("usuario")
        row = consultar("SELECT senha_hash FROM usuarios WHERE usuario = %s", (usuario,), um=True)

        if not row or not check_password_hash(row["senha_hash"], senha_atual):
            flash("Senha atual incorreta.", "erro")
            return render_template("trocar_senha.html", bebida=BEBIDA), 400

        if len(nova_senha) < 6:
            flash("A nova senha deve ter no mínimo 6 caracteres.", "erro")
            return render_template("trocar_senha.html", bebida=BEBIDA), 400

        if len(nova_senha) > 128:
            flash("A nova senha não pode ter mais de 128 caracteres.", "erro")
            return render_template("trocar_senha.html", bebida=BEBIDA), 400

        if nova_senha != confirmar_nova:
            flash("A confirmação da nova senha não confere.", "erro")
            return render_template("trocar_senha.html", bebida=BEBIDA), 400

        nova_hash = generate_password_hash(nova_senha)
        executar("UPDATE usuarios SET senha_hash = %s WHERE usuario = %s", (nova_hash, usuario))
        flash("Senha alterada com sucesso!", "ok")
        return redirect(url_for("index"))

    return render_template("trocar_senha.html", bebida=BEBIDA)


@app.route("/adicionar-contribuinte", methods=["GET", "POST"])
def adicionar_contribuinte():
    if session.get("dono"):
        flash("Apenas a conta principal pode adicionar contribuintes.", "erro")
        return redirect(url_for("index"))

    dono = session.get("usuario")

    if request.method == "POST":
        usuario = request.form.get("usuario", "").strip()
        senha = request.form.get("senha", "")
        confirmar_senha = request.form.get("confirmar_senha", "")

        if not usuario or len(usuario) < 3 or len(usuario) > 50:
            flash("O nome de usuário deve ter entre 3 e 50 caracteres.", "erro")
            return redirect(url_for("adicionar_contribuinte"))

        if not re.fullmatch(r"[A-Za-z0-9_.-]+", usuario):
            flash("O usuário deve conter apenas letras, números, sublinhado (_), hífen (-) e ponto (.).", "erro")
            return redirect(url_for("adicionar_contribuinte"))

        if len(senha) < 6:
            flash("A senha deve ter no mínimo 6 caracteres.", "erro")
            return redirect(url_for("adicionar_contribuinte"))

        if len(senha) > 128:
            flash("A senha não pode ter mais de 128 caracteres.", "erro")
            return redirect(url_for("adicionar_contribuinte"))

        if senha != confirmar_senha:
            flash("As senhas informadas não conferem.", "erro")
            return redirect(url_for("adicionar_contribuinte"))

        existente = consultar("SELECT id FROM usuarios WHERE usuario = %s", (usuario,), um=True)
        if existente:
            flash("Este nome de usuário já está em uso.", "erro")
            return redirect(url_for("adicionar_contribuinte"))

        senha_hash = generate_password_hash(senha)
        try:
            executar("INSERT INTO usuarios (usuario, senha_hash) VALUES (%s, %s)",
                     (usuario, senha_hash))
            executar("INSERT INTO contribuintes (dono, contribuinte) VALUES (%s, %s)",
                     (dono, usuario))
        except pymysql.err.IntegrityError:
            flash("Este nome de usuário já está em uso.", "erro")
            return redirect(url_for("adicionar_contribuinte"))

        flash(f"Contribuinte '{usuario}' adicionado com sucesso! Ele já tem acesso ao seu estoque.", "ok")
        return redirect(url_for("adicionar_contribuinte"))

    contribuintes = consultar(
        """SELECT id, contribuinte, criado_em 
           FROM contribuintes 
           WHERE dono = %s 
           ORDER BY id DESC""",
        (dono,),
    )
    return render_template(
        "adicionar_contribuinte.html",
        bebida=BEBIDA,
        contribuintes=contribuintes,
    )


@app.route("/remover-contribuinte/<int:contrib_id>", methods=["POST"])
def remover_contribuinte(contrib_id):
    if session.get("dono"):
        flash("Apenas a conta principal pode remover contribuintes.", "erro")
        return redirect(url_for("index"))

    dono = session.get("usuario")
    contrib = consultar(
        "SELECT id, contribuinte FROM contribuintes WHERE id = %s AND dono = %s",
        (contrib_id, dono),
        um=True,
    )
    if not contrib:
        flash("Contribuinte não encontrado.", "erro")
        return redirect(url_for("adicionar_contribuinte"))

    nome_contrib = contrib["contribuinte"]
    # Reatribui movimentações para o dono preservando anotação de quem fez
    executar(
        "UPDATE movimentos SET usuario = %s, sabor = CONCAT('[Ex-contrib. ', %s, '] ', COALESCE(sabor, '')) WHERE usuario = %s",
        (dono, nome_contrib, nome_contrib),
    )
    executar("DELETE FROM contribuintes WHERE id = %s", (contrib_id,))
    executar("DELETE FROM usuarios WHERE usuario = %s", (nome_contrib,))
    flash(f"Contribuinte '{nome_contrib}' removido com sucesso.", "ok")
    origem = request.referrer or url_for("index")
    return redirect(origem)


@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    flash("Você saiu do sistema.", "ok")
    return redirect(url_for("login"))


# ============================ computador ====================================
@app.route("/")
def index():
    conta = conta_estoque_atual()
    total = estoque_atual(conta)
    historico = consultar(
        """SELECT * FROM movimentos 
           WHERE (usuario = %s OR usuario IN (SELECT contribuinte FROM contribuintes WHERE dono = %s))
           ORDER BY id DESC LIMIT 20""",
        (conta, conta),
    )
    contribuintes = []
    if not session.get("dono"):
        contribuintes = consultar(
            """SELECT id, contribuinte, criado_em 
               FROM contribuintes 
               WHERE dono = %s 
               ORDER BY id DESC""",
            (session.get("usuario"),),
        )

    return render_template(
        "index.html",
        bebida=BEBIDA, embalagem=EMBALAGEM, total=total,
        por_caixa=UNIDADES_POR_CAIXA,
        caixas=total // UNIDADES_POR_CAIXA,
        avulsas=total % UNIDADES_POR_CAIXA,
        valor=total * PRECO_UNIDADE,
        minimo=ESTOQUE_MINIMO, baixo=total < ESTOQUE_MINIMO,
        historico=historico,
        contribuintes=contribuintes,
    )


@app.route("/movimentar", methods=["POST"])
def movimentar():
    conta = conta_estoque_atual()
    tipo = request.form.get("tipo")
    sabor = request.form.get("sabor", "").strip()
    qtd = ler_quantidade(request.form.get("quantidade"))

    total = estoque_atual(conta)
    if tipo not in ("entrada", "saida") or qtd <= 0:
        flash("Informe uma quantidade válida (de 1 a 10000).", "erro")
    elif tipo == "saida" and qtd > total:
        flash(f"Saída maior que o estoque. Disponível: {total} unidades.", "erro")
    else:
        registrar(tipo, qtd, sabor, session.get("usuario"))
        flash(texto_movimento(tipo, qtd), "ok")
    return redirect(url_for("index"))


@app.route("/desfazer/<int:mov_id>", methods=["POST"])
def desfazer(mov_id):
    conta = conta_estoque_atual()
    mov = consultar(
        """SELECT tipo, quantidade FROM movimentos 
           WHERE id = %s AND (usuario = %s OR usuario IN (SELECT contribuinte FROM contribuintes WHERE dono = %s))""",
        (mov_id, conta, conta),
        um=True,
    )
    if mov is None:
        flash("Movimentação não encontrada.", "erro")
    else:
        efeito = mov["quantidade"] if mov["tipo"] == "entrada" else -mov["quantidade"]
        if estoque_atual(conta) - efeito < 0:
            flash("Não dá para remover: o estoque ficaria negativo.", "erro")
        else:
            executar("DELETE FROM movimentos WHERE id = %s", (mov_id,))
            flash("Movimentação removida.", "ok")
    return redirect(url_for("index"))


# ============================ celular =======================================
@app.route("/celular")
def celular():
    conta = conta_estoque_atual()
    total = estoque_atual(conta)
    historico = consultar(
        """SELECT * FROM movimentos 
           WHERE (usuario = %s OR usuario IN (SELECT contribuinte FROM contribuintes WHERE dono = %s))
           ORDER BY id DESC LIMIT 20""",
        (conta, conta),
    )
    contribuintes = []
    if not session.get("dono"):
        contribuintes = consultar(
            "SELECT id, contribuinte, criado_em FROM contribuintes WHERE dono = %s ORDER BY id DESC",
            (session.get("usuario"),),
        )
    return render_template(
        "celular.html",
        bebida=BEBIDA, embalagem=EMBALAGEM, total=total,
        por_caixa=UNIDADES_POR_CAIXA,
        caixas=total // UNIDADES_POR_CAIXA,
        avulsas=total % UNIDADES_POR_CAIXA,
        valor=total * PRECO_UNIDADE,
        minimo=ESTOQUE_MINIMO, baixo=total < ESTOQUE_MINIMO,
        historico=historico,
        contribuintes=contribuintes,
    )


@app.route("/movimentar-celular", methods=["POST"])
def movimentar_celular():
    conta = conta_estoque_atual()
    tipo = request.form.get("tipo")
    sabor = request.form.get("sabor", "").strip()
    qtd = ler_quantidade(request.form.get("quantidade"))

    total = estoque_atual(conta)
    if tipo not in ("entrada", "saida") or qtd <= 0:
        flash("Informe uma quantidade válida (de 1 a 10000).", "erro")
    elif tipo == "saida" and qtd > total:
        flash(f"Saída maior que o estoque. Disponível: {total} unidades.", "erro")
    else:
        registrar(tipo, qtd, sabor, session.get("usuario"))
        flash(texto_movimento(tipo, qtd), "ok")
    return redirect(url_for("celular"))


@app.route("/desfazer-celular/<int:mov_id>", methods=["POST"])
def desfazer_celular(mov_id):
    conta = conta_estoque_atual()
    mov = consultar(
        """SELECT tipo, quantidade FROM movimentos 
           WHERE id = %s AND (usuario = %s OR usuario IN (SELECT contribuinte FROM contribuintes WHERE dono = %s))""",
        (mov_id, conta, conta),
        um=True,
    )
    if mov is None:
        flash("Movimentação não encontrada.", "erro")
    else:
        efeito = mov["quantidade"] if mov["tipo"] == "entrada" else -mov["quantidade"]
        if estoque_atual(conta) - efeito < 0:
            flash("Não dá para remover: o estoque ficaria negativo.", "erro")
        else:
            executar("DELETE FROM movimentos WHERE id = %s", (mov_id,))
            flash("Movimentação removida.", "ok")
    return redirect(url_for("celular"))


# ============================ QR code =======================================
def ip_da_maquina():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def url_do_celular():
    if URL_BASE:
        base = URL_BASE.rstrip("/")
    else:
        host = request.host.split(":")[0]
        if host in ("127.0.0.1", "localhost"):
            base = f"http://{ip_da_maquina()}:{PORTA}"
        else:
            base = request.host_url.rstrip("/")
    return base + url_for("celular")


@app.route("/qr.svg")
def qr_svg():
    img = qrcode.make(url_do_celular(),
                      image_factory=qrcode.image.svg.SvgPathImage, box_size=10)
    buf = BytesIO()
    img.save(buf)
    return Response(buf.getvalue(), mimetype="image/svg+xml")


@app.route("/qr")
def qr_pagina():
    return render_template("qr.html", bebida=BEBIDA, link=url_do_celular())


if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=PORTA, debug=DEBUG)
