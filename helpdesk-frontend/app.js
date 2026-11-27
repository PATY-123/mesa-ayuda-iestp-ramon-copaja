// Usa la URL local si se abre desde localhost/127.0.0.1; si está publicado en el mismo dominio, usa ruta relativa ""
const esLocal =
  window.location.hostname === "127.0.0.1" ||
  window.location.hostname === "localhost";

// En local apunta a Flask (5001); al publicarse en el mismo origen usa "" (o pon aquí la URL pública de tu API)
const BASE_URL = "https://mesa-ayuda-iestp-api.onrender.com";

// Obtiene referencias a los elementos del formulario, tabla, mensajes y botón en index.html
const frm = document.getElementById("frm");
const tbody = document.getElementById("tbody");
const msg = document.getElementById("msg");
const btnCargar = document.getElementById("btnCargar");

// Muestra un mensaje de alerta ("ok" en verde o "err" en rojo) dentro de #msg
function showMsg(type, text) {
  msg.classList.remove("d-none", "alert-success", "alert-danger"); // Limpia clases previas
  msg.classList.add(type === "ok" ? "alert-success" : "alert-danger"); // Aplica estilo según tipo
  msg.textContent = text; // Escribe el texto del mensaje
}

// Renderiza las filas de tickets dentro del cuerpo de la tabla (<tbody id="tbody">)
function renderTickets(list) {
  if (!Array.isArray(list) || list.length === 0) { // Valida que haya tickets para mostrar
    tbody.innerHTML = '<tr><td colspan="6" class="text-center text-muted py-4">Sin tickets</td></tr>';
    return;
  }

  tbody.innerHTML = list.map((t) => `
    <tr>
      <td class="fw-semibold">${t.id ?? ""}</td>
      <td>${t.titulo ?? ""}</td>
      <td>${t.categoria ?? ""}</td>
      <td>${t.prioridad ?? ""}</td>
      <td>${t.estado ?? ""}</td>
      <td>${t.creado_en ?? ""}</td>
    </tr>
  `).join(""); // Une todas las filas HTML y las inserta en la tabla
}

// Consulta GET /api/tickets y actualiza la tabla de tickets
async function cargarTickets() {
  try {
    const res = await fetch(`${BASE_URL}/api/tickets`); // Llama al endpoint GET de tickets
    const data = await res.json(); // Convierte la respuesta JSON a objeto/arreglo

    if (!res.ok) { // Si el código HTTP no es 2xx, lanza error con el mensaje del servidor
      throw new Error(data.error || "Error al cargar tickets");
    }

    const lista = Array.isArray(data) ? data : (data.data || data.tickets || []); // Normaliza formato de lista
    renderTickets(lista); // Dibuja los tickets en pantalla
  } catch (err) {
    showMsg("err", err.message || "No se pudo conectar con la API"); // Muestra error si falla la red o API
  }
}

// Envía POST /api/tickets en formato JSON para crear un nuevo ticket
async function registrarTicket(payload) {
  const res = await fetch(`${BASE_URL}/api/tickets`, {
    method: "POST", // Método HTTP para crear recurso
    headers: { "Content-Type": "application/json" }, // Indica que el cuerpo va en JSON
    body: JSON.stringify(payload) // Serializa los datos del ticket a texto JSON
  });

  const data = await res.json(); // Lee la respuesta del servidor

  if (!res.ok) { // Si hubo validación fallida o error, detiene y muestra el motivo
    throw new Error(data.error || "Error al registrar ticket");
  }

  return data; // Devuelve el ticket creado
}

// Escucha el envío del formulario para registrar el ticket y refrescar la lista
frm.addEventListener("submit", async (e) => {
  e.preventDefault(); // Evita que la página se recargue por defecto al enviar el formulario

  try {
    const payload = { // Construye el objeto con los campos del formulario
      titulo: document.getElementById("titulo").value.trim(),
      descripcion: document.getElementById("descripcion").value.trim(),
      categoria: document.getElementById("categoria").value.trim() || "General",
      prioridad: document.getElementById("prioridad").value
    };

    await registrarTicket(payload); // Envía el ticket al backend
    showMsg("ok", "Ticket registrado correctamente."); // Informa éxito al usuario

    frm.reset(); // Limpia los campos del formulario
    document.getElementById("categoria").value = "General"; // Restaura categoría por defecto
    document.getElementById("prioridad").value = "Media"; // Restaura prioridad por defecto

    await cargarTickets(); // Recarga la tabla para mostrar el ticket recién creado
  } catch (err) {
    showMsg("err", err.message); // Muestra error si no se pudo registrar
  }
});

// Asocia el clic del botón "Cargar tickets" a la función cargarTickets
btnCargar.addEventListener("click", cargarTickets);

// Ejecuta la carga inicial de tickets apenas abre la página
cargarTickets();