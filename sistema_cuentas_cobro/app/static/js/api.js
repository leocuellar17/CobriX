/**
 * Cliente HTTP centralizado para los endpoints REST /api/v1/* de CobriX.
 */

const API_BASE = "/api/v1";

async function request(endpoint, options = {}) {
    const config = {
        headers: {
            ...(options.body instanceof FormData ? {} : { "Content-Type": "application/json" }),
            ...(options.headers || {}),
        },
        ...options,
    };

    const response = await fetch(`${API_BASE}${endpoint}`, config);

    if (response.status === 204) {
        return null;
    }

    const contentType = response.headers.get("content-type") || "";
    const data = contentType.includes("application/json")
        ? await response.json()
        : await response.text();

    if (!response.ok) {
        let mensaje = "Ocurrió un error inesperado al procesar la solicitud.";
        if (typeof data === "object" && data !== null) {
            if (typeof data.detail === "string") {
                mensaje = data.detail;
            } else if (Array.isArray(data.detail) && data.detail.length > 0) {
                mensaje = data.detail.map((err) => err.msg || String(err)).join(" · ");
            }
        }
        throw new Error(mensaje);
    }

    return data;
}

export const api = {
    // Emisor
    obtenerEmisor() {
        return request("/emisor");
    },
    actualizarEmisor(payload) {
        return request("/emisor", {
            method: "PUT",
            body: JSON.stringify(payload),
        });
    },
    subirArchivoEmisor(tipo, file) {
        const formData = new FormData();
        formData.append("file", file);
        return request(`/emisor/archivos/${tipo}`, {
            method: "POST",
            body: formData,
        });
    },

    // Clientes
    listarClientes({ soloActivos = true, busqueda = "" } = {}) {
        const params = new URLSearchParams();
        params.set("solo_activos", String(soloActivos));
        if (busqueda && busqueda.trim()) {
            params.set("busqueda", busqueda.trim());
        }
        return request(`/clientes?${params.toString()}`);
    },
    crearCliente(payload) {
        return request("/clientes", {
            method: "POST",
            body: JSON.stringify(payload),
        });
    },
    actualizarCliente(clienteId, payload) {
        return request(`/clientes/${clienteId}`, {
            method: "PUT",
            body: JSON.stringify(payload),
        });
    },
    cambiarEstadoCliente(clienteId, activo) {
        return request(`/clientes/${clienteId}/estado`, {
            method: "PATCH",
            body: JSON.stringify({ activo }),
        });
    },

    // Tablero y Cuentas de Cobro
    obtenerTablero(periodoMes) {
        return request(`/tablero/${encodeURIComponent(periodoMes)}`);
    },
    iniciarMes(periodoMes) {
        return request("/cuentas/iniciar-mes", {
            method: "POST",
            body: JSON.stringify({ periodo_mes: periodoMes }),
        });
    },
    crearCobroManual(payload) {
        return request("/cuentas/manual", {
            method: "POST",
            body: JSON.stringify(payload),
        });
    },
    emitirCuenta(cuentaId, payload) {
        return request(`/cuentas/${cuentaId}/emitir`, {
            method: "PUT",
            body: JSON.stringify(payload),
        });
    },
    cambiarPagoCuenta(cuentaId, pagada, fechaPago = null) {
        return request(`/cuentas/${cuentaId}/pago`, {
            method: "PATCH",
            body: JSON.stringify({ pagada, fecha_pago: fechaPago }),
        });
    },
    anularCuenta(cuentaId, observaciones = null) {
        return request(`/cuentas/${cuentaId}/anular`, {
            method: "PATCH",
            body: JSON.stringify({ observaciones_internas: observaciones }),
        });
    },
    eliminarBorrador(cuentaId) {
        return request(`/cuentas/${cuentaId}`, {
            method: "DELETE",
        });
    },
    urlPdfCuenta(cuentaId, { incluirAnexos = true, regenerar = false } = {}) {
        const params = new URLSearchParams({
            incluir_anexos: String(incluirAnexos),
            regenerar: String(regenerar),
        });
        return `${API_BASE}/cuentas/${cuentaId}/pdf?${params.toString()}`;
    },

    // Utilidad de sistema local
    abrirCarpetaPeriodo(periodoMes) {
        return request(`/sistema/abrir-carpeta/${encodeURIComponent(periodoMes)}`, {
            method: "POST",
        });
    },
    crearRespaldo() {
        return request("/sistema/backup", {
            method: "POST",
        });
    },
    apagarSistema() {
        return request("/sistema/apagar", {
            method: "POST",
        });
    },
};
