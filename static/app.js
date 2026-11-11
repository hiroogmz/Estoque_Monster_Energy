// Pedir confirmação antes de enviar formulários marcados com data-confirmar
document.addEventListener("submit", function (e) {
  var msg = e.target.getAttribute("data-confirmar");
  if (msg && !window.confirm(msg)) e.preventDefault();
});

// Botão de imprimir da página do QR code
document.addEventListener("click", function (e) {
  if (e.target.closest("[data-imprimir]")) window.print();
});

// Alternar visibilidade de senha (mostrar / ocultar)
document.addEventListener("click", function (e) {
  var btn = e.target.closest(".btn-toggle-senha");
  if (!btn) return;

  var alvoId = btn.getAttribute("data-alvo");
  var input = document.getElementById(alvoId);
  if (!input) return;

  if (input.type === "password") {
    input.type = "text";
    btn.classList.add("ativo");
    btn.setAttribute("aria-label", "Ocultar senha");
  } else {
    input.type = "password";
    btn.classList.remove("ativo");
    btn.setAttribute("aria-label", "Mostrar senha");
  }
});

// Validação visual de confirmação de senha
function checarCoincidenciaSenhas(idSenha, idConfirma, idAviso) {
  var senha = document.getElementById(idSenha);
  var confirma = document.getElementById(idConfirma);
  var aviso = document.getElementById(idAviso);
  if (!senha || !confirma || !aviso) return;

  function validar() {
    if (!confirma.value) {
      aviso.textContent = "";
      aviso.style.display = "none";
      return;
    }
    if (senha.value !== confirma.value) {
      aviso.textContent = "As senhas não coincidem.";
      aviso.style.color = "var(--vermelho)";
      aviso.style.display = "block";
    } else {
      aviso.textContent = "As senhas coincidem!";
      aviso.style.color = "var(--verde)";
      aviso.style.display = "block";
    }
  }

  senha.addEventListener("input", validar);
  confirma.addEventListener("input", validar);
}

document.addEventListener("DOMContentLoaded", function () {
  checarCoincidenciaSenhas("senha", "confirmar_senha", "aviso-confirma-senha");
  checarCoincidenciaSenhas("nova_senha", "confirmar_nova", "aviso-confirma-nova");
});
