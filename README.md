# Estoque_Monster_Energy
Um estoque inteligente de Energético Monster para Frigobar
Sistema web de controle de estoque para um frigobar de Monster Energy, criado para facilitar a contagem das latas sem precisar conferir tudo na mão.

**Sobre o projeto:**
Manter um frigobar pode ser díficil, ainda mais em uma casa com muitas pessoas, então decidimos criar esse projeto especificamente para energético, isso ajudaria não só o pessoal mais gamer, mas também em festas, que por muitas vezes têm um público mais jovem que consome energético. Saber quantas latas restam, de quais sabores e quando é hora de repor. Este projeto resolve isso com um painel simples: o usuário escaneia o QR code do frigobar, registra o consumo em poucos toques e o sistema mantém a contagem atualizada para todos que têm acesso.

**Objetivos:**
- Facilitar a contagem das latas de Monster no frigobar
- Registrar entradas (reposição) e saídas (consumo), com o sabor de cada lata
- Avisar quando o estoque estiver baixo (estoque mínimo configurável)
- Permitir o uso rápido pelo celular, com acesso por QR code
- Proteger o acesso ao sistema com login e senha (Cyber Security)
- Registrar o nome dos usuários que têm acesso ao frigobar para que não desorganize

**O que a solução se propõe a resolver:**
Contagem total atualizada, também em caixas + avulsas;
Alerta de estoque abaixo do mínimo (padrão: 6 unidades);
Registro de entrada/saída em poucos toques, inclusive no celular;
Valor total em reais calculado automaticamente (Pode variar o preço, então isso é uma estimativa;
Histórico com data, tipo, quantidade, sabor e usuário;
Login com senha criptografada, proteção contra força bruta e CSRF;

**Funcionalidades do projeto:**
- Cadastro de entrada e saída de latas
- Controle de sabores
- Alerta de estoque baixo
- Tela de login e senha
- Interface para computador e versão para celular
- Acesso rápido por QR code
- Criação automática do banco de dados e das tabelas

- **Painel do estoque:** total de unidades, caixas + avulsas, valor em estoque e alerta de reposição
- **Movimentações:** registro de entrada e saída, com sabor opcional; bloqueio de saída maior que o estoque
- **Histórico:** últimas 20 movimentações, com opção de remover (sem deixar o estoque negativo)
- **Versão para celular:** tela com botões grandes
- **QR code do frigobar:** gerado pelo sistema, com opção de imprimir
- **Login e cadastro de usuários**, com troca de senha
- **Contas supervisor e contribuintes:** o supervisor cria contribuintes que movimentam o mesmo estoque; ao remover um contribuinte, o histórico dele é preservado
- **Criação automática** do banco, das tabelas e do primeiro usuário administrador

**Segurança:**
- Senhas armazenadas com **hash** (Werkzeug), nunca em texto puro
- **Bloqueio de tentativas de login** por IP (5) e por usuário (10) em janela de 15 minutos
- Proteção contra **CSRF** em todos os formulários (Flask-WTF)
- Proteção contra **SQL Injection** com consultas parametrizadas
- Cookies de sessão https, com expiração em 30 minutos
- Resposta de login com tempo uniforme, para não revelar quais usuários existem
- Credenciais do banco e chave secreta fora do código, em arquivo `.env`
- Limite de tamanho das requisições

**Tecnologias utilizadas:**
- Linguagem - Python 3 -
- Back-end - Flask 3, Flask-WTF (CSRF), Werkzeug (hash de senhas) -
- Banco de dados - MySQL (InnoDB), acessado com PyMySQL -
- Front-end - HTML5 (templates Jinja2), CSS3, JavaScript puro -
- QR code - Biblioteca `qrcode` (saída em SVG) -
- Configuração - `python-dotenv` (arquivo `.env`) -
- Criptografia - `cryptography` (autenticação do MySQL) -
- Ambiente - Máquina virtual Windows -
- Rede - Aplicação web sobre HTTP/TCP (porta 5000); MySQL sobre TCP (porta 3306); administração da VM via SSH -
- Editor - Visual Studio Code -

**Banco de dados:**
Banco `estoque`, com quatro tabelas:
- `usuarios`: contas do sistema (com hash da senha)
- `movimentos`: entradas e saídas, com quantidade, sabor, usuário e data
- `contribuintes`: vínculo entre o supervisor e seus contribuintes
- `tentativas_login`: controle contra ataques de força bruta

**Como executar:**

```bash
# 1. Clonar o repositório
git clone [URL-DO-REPOSITORIO]
cd [NOME-DA-PASTA]

# 2. Instalar as dependências
py -m pip install -r requirements.txt

# 3. Criar o banco e o usuário no MySQL (como administrador)
mysql -u root -p < banco.sql

# 4. Criar o arquivo .env a partir do .env.example
#    e preencher DB_SENHA, SECRET_KEY e, se quiser, ADMIN_USUARIO / ADMIN_SENHA

# 5. Iniciar o sistema
py app.py
```

- Computador: `http://127.0.0.1:5000`
- Celular: `/celular`, ou escaneie o QR code em `/qr` (o celular precisa estar na mesma rede Wi-Fi da VM)

Para criar ou redefinir um usuário pelo terminal: `py criar_usuario.py`

**Melhorias futuras:**

- Contagem automática ao colocar/retirar latas, com balança ou webcam lendo código de barras;
- Tabela própria de sabores, em vez de campo livre;
- Relatórios de consumo por período;
- HTTPS na aplicação;

**Equipe que desenvolveu o projeto:**
- Enzo Hiroshi Guizi Onomura
- Miguel Ávila de Almeida
- Guilherme Pedro dos Santos
- Gustavo Henrique de Souza
- Maria Eduarda De Lima Campos
