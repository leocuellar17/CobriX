/**
 * Utilidades de formateo en español colombiano (COP, fechas, periodos y archivos).
 */

const MESES_ES = [
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"
];

const MESES_TITULO_ES = [
    "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
    "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"
];

export function obtenerPeriodoActual() {
    const ahora = new Date();
    const anio = ahora.getFullYear();
    const mes = String(ahora.getMonth() + 1).padStart(2, "0");
    return `${anio}-${mes}`;
}

export function obtenerFechaHoyISO() {
    const ahora = new Date();
    const anio = ahora.getFullYear();
    const mes = String(ahora.getMonth() + 1).padStart(2, "0");
    const dia = String(ahora.getDate()).padStart(2, "0");
    return `${anio}-${mes}-${dia}`;
}

export function desplazarPeriodo(periodoMes, deltaMeses) {
    const [anioStr, mesStr] = periodoMes.split("-");
    const fecha = new Date(Number(anioStr), Number(mesStr) - 1 + deltaMeses, 1);
    const nuevoAnio = fecha.getFullYear();
    const nuevoMes = String(fecha.getMonth() + 1).padStart(2, "0");
    return `${nuevoAnio}-${nuevoMes}`;
}

export function formatearPeriodoLegible(periodoMes) {
    if (!periodoMes || !periodoMes.includes("-")) return periodoMes || "";
    const [anio, mesStr] = periodoMes.split("-");
    const idx = Number(mesStr) - 1;
    const nombreMes = MESES_TITULO_ES[idx] || mesStr;
    return `${nombreMes} ${anio}`;
}

export function formatearMonedaCOP(valor) {
    const numero = Number(valor || 0);
    if (Number.isNaN(numero)) return "$ 0";
    const entero = Math.round(numero);
    const texto = entero.toLocaleString("es-CO");
    return `$ ${texto}`;
}

export function formatearFechaCorta(fechaISO) {
    if (!fechaISO) return "";
    const partes = fechaISO.split("-");
    if (partes.length !== 3) return fechaISO;
    const [anio, mesStr, diaStr] = partes;
    const nombreMes = MESES_ES[Number(mesStr) - 1] || mesStr;
    return `${Number(diaStr)} de ${nombreMes} de ${anio}`;
}

export function limpiarSoloDigitos(texto) {
    return String(texto || "").replace(/\D/g, "");
}

export function formatearInputMilesCOP(valorNumericoStr) {
    const digitos = limpiarSoloDigitos(valorNumericoStr);
    if (!digitos) return "";
    return `$ ${Number(digitos).toLocaleString("es-CO")}`;
}

export function extraerNombreArchivo(rutaCompleta) {
    if (!rutaCompleta) return "";
    const partes = String(rutaCompleta).split(/[/\\]/);
    return partes[partes.length - 1] || "";
}
