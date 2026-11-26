/**
 * Store reactivo principal de Alpine.js para CobriX.
 */

import { api } from "./api.js";
import {
    desplazarPeriodo,
    extraerNombreArchivo,
    formatearFechaCorta,
    formatearInputMilesCOP,
    formatearMonedaCOP,
    formatearPeriodoLegible,
    limpiarSoloDigitos,
    obtenerFechaHoyISO,
    obtenerPeriodoActual,
} from "./utils.js";

window.cobrixApp = function cobrixApp() {
    return {
        // Navegación y estado global
        pestanaActiva: "tablero",
        periodoMes: obtenerPeriodoActual(),
        cargandoTablero: false,
        cargandoAccion: false,
        firmaCacheBust: Date.now(),

        // Datos de dominio
        emisor: {
            nombre_completo: "",
            tipo_documento: "C.C.",
            numero_documento: "",
            rut: "",
            direccion: "",
            ciudad: "Bogotá D.C.",
            telefono: "",
            correo: "",
            banco: "",
            tipo_cuenta: "Ahorros",
            numero_cuenta: "",
            nota_legal_iva: "",
            nota_retencion: "",
            ruta_firma: null,
            ruta_rut_pdf: null,
            ruta_cert_bancaria_pdf: null,
        },
        tablero: {
            periodo_mes: obtenerPeriodoActual(),
            cuentas_del_mes: [],
            cartera_vencida: [],
            kpis: {
                total_facturado_mes: "0.00",
                total_recaudado_mes: "0.00",
                total_por_cobrar_mes: "0.00",
                total_cartera_vencida_historica: "0.00",
                pendientes_por_redactar: 0,
            },
        },
        filtroTodo: "TODAS",

        // Directorio de clientes
        clientes: [],
        busquedaClientes: "",
        mostrarInactivos: false,

        // Modal de Redacción / Emisión de Cuenta
        modalCuentaAbierto: false,
        modalCuentaModo: "emitir", // "emitir" | "editar" | "manual"
        cuentaForm: {
            id: null,
            cliente_id: "",
            cliente_nombre: "",
            cliente_documento: "",
            cliente_tipo_persona: "",
            fecha_emision: obtenerFechaHoyISO(),
            valor_digitos: "",
            concepto_honorarios: "",
            observaciones_internas: "",
            incluir_anexos: true,
        },
        conceptoMesPasado: null,
        cargandoMesPasado: false,

        // Modal de Cliente
        modalClienteAbierto: false,
        clienteEditandoId: null,
        clienteForm: {
            tipo_persona: "JURIDICA",
            nombre_razon_social: "",
            documento_nit: "",
            ciudad: "Bogotá D.C.",
            direccion: "",
            correo_contacto: "",
            telefono: "",
            es_recurrente: true,
        },

        // Notificaciones Toast estilo Windows 11
        toasts: [],

        // Helpers expuestos al HTML
        formatearMonedaCOP,
        formatearFechaCorta,
        formatearPeriodoLegible,
        extraerNombreArchivo,

        async init() {
            await Promise.all([
                this.cargarEmisor(),
                this.cargarTablero(),
                this.cargarClientes(),
            ]);
            this.refrescarIconos();
        },

        refrescarIconos() {
            this.$nextTick(() => {
                if (window.lucide) {
                    window.lucide.createIcons();
                }
            });
        },

        notificar(mensaje, tipo = "info") {
            const id = Date.now() + Math.random();
            this.toasts.push({ id, mensaje, tipo });
            this.refrescarIconos();
            setTimeout(() => {
                this.toasts = this.toasts.filter((t) => t.id !== id);
            }, 4200);
        },

        // -------------------------------------------------------------------
        // Navegación y Periodo
        // -------------------------------------------------------------------

        cambiarPestana(nombre) {
            this.pestanaActiva = nombre;
            this.refrescarIconos();
        },

        async cambiarPeriodo(delta) {
            this.periodoMes = desplazarPeriodo(this.periodoMes, delta);
            await this.cargarTablero();
        },

        async onCambioPeriodoInput() {
            if (/^\d{4}-(0[1-9]|1[0-2])$/.test(this.periodoMes)) {
                await this.cargarTablero();
            }
        },

        // -------------------------------------------------------------------
        // Tablero y To-Do List
        // -------------------------------------------------------------------

        async cargarTablero() {
            this.cargandoTablero = true;
            try {
                this.tablero = await api.obtenerTablero(this.periodoMes);
            } catch (err) {
                this.notificar(err.message, "error");
            } finally {
                this.cargandoTablero = false;
                this.refrescarIconos();
            }
        },

        get cuentasFiltradas() {
            const lista = this.tablero.cuentas_del_mes || [];
            if (this.filtroTodo === "TODAS") {
                return lista.filter((c) => c.estado !== "ANULADA");
            }
            return lista.filter((c) => c.estado === this.filtroTodo);
        },

        get valorVistaPreviaCOP() {
            if (!this.cuentaForm.valor_digitos) return "$ 0";
            return formatearInputMilesCOP(this.cuentaForm.valor_digitos);
        },

        onInputValorHonorarios(event) {
            const digitos = limpiarSoloDigitos(event.target.value);
            this.cuentaForm.valor_digitos = digitos;
        },

        async iniciarMes() {
            this.cargandoAccion = true;
            try {
                const res = await api.iniciarMes(this.periodoMes);
                if (res.creadas > 0) {
                    this.notificar(
                        `Se crearon ${res.creadas} tareas nuevas de cobro para ${formatearPeriodoLegible(this.periodoMes)}.`,
                        "success"
                    );
                } else {
                    this.notificar(
                        `Todos tus clientes recurrentes (${res.ya_existentes}) ya están cargados en este mes.`,
                        "info"
                    );
                }
                await this.cargarTablero();
            } catch (err) {
                this.notificar(err.message, "error");
            } finally {
                this.cargandoAccion = false;
            }
        },

        async abrirCarpetaPDFs() {
            try {
                await api.abrirCarpetaPeriodo(this.periodoMes);
                this.notificar(
                    `Carpeta de ${formatearPeriodoLegible(this.periodoMes)} abierta en el explorador.`,
                    "info"
                );
            } catch (err) {
                this.notificar(err.message, "error");
            }
        },

        async crearRespaldoManual() {
            this.cargandoAccion = true;
            try {
                const res = await api.crearRespaldo();
                this.notificar(`Copia de seguridad creada: ${res.archivo}`, "success");
            } catch (err) {
                this.notificar(err.message, "error");
            } finally {
                this.cargandoAccion = false;
            }
        },

        async apagarSistema() {
            if (!window.confirm("¿Deseas guardar una copia de seguridad y cerrar la aplicación?")) {
                return;
            }
            this.cargandoAccion = true;
            try {
                await api.apagarSistema();
                this.notificar("Respaldo guardado. Ya puedes cerrar esta pestaña.", "success");
            } catch (err) {
                this.notificar(err.message, "error");
            } finally {
                this.cargandoAccion = false;
            }
        },

        async togglePagoCuenta(cuenta) {
            if (cuenta.estado === "BORRADOR") return;
            const marcarPagada = cuenta.estado !== "PAGADA";
            try {
                await api.cambiarPagoCuenta(
                    cuenta.id,
                    marcarPagada,
                    marcarPagada ? obtenerFechaHoyISO() : null
                );
                this.notificar(
                    marcarPagada
                        ? `Cuenta ${cuenta.consecutivo} marcada como pagada.`
                        : `Cuenta ${cuenta.consecutivo} devuelta a Por Cobrar.`,
                    marcarPagada ? "success" : "info"
                );
                await this.cargarTablero();
            } catch (err) {
                this.notificar(err.message, "error");
            }
        },

        async eliminarBorrador(cuenta) {
            if (cuenta.estado !== "BORRADOR") return;
            try {
                await api.eliminarBorrador(cuenta.id);
                this.notificar(
                    `Borrador de ${cuenta.cliente.nombre_razon_social} eliminado de este mes.`,
                    "info"
                );
                await this.cargarTablero();
            } catch (err) {
                this.notificar(err.message, "error");
            }
        },

        verPdfCuenta(cuentaId, incluirAnexos = true, regenerar = false) {
            const url = api.urlPdfCuenta(cuentaId, { incluirAnexos, regenerar });
            window.open(url, "_blank", "noopener");
        },

        // -------------------------------------------------------------------
        // Modal de Redacción / Emisión de Honorarios
        // -------------------------------------------------------------------

        async abrirModalEmitir(cuenta) {
            this.modalCuentaModo = cuenta.estado === "BORRADOR" ? "emitir" : "editar";
            this.cuentaForm = {
                id: cuenta.id,
                cliente_id: cuenta.cliente_id,
                cliente_nombre: cuenta.cliente.nombre_razon_social,
                cliente_documento: cuenta.cliente.documento_nit,
                cliente_tipo_persona: cuenta.cliente.tipo_persona,
                fecha_emision: cuenta.fecha_emision || obtenerFechaHoyISO(),
                valor_digitos: Number(cuenta.valor_total) > 0
                    ? String(Math.round(Number(cuenta.valor_total)))
                    : "",
                concepto_honorarios: cuenta.concepto_honorarios || "",
                observaciones_internas: cuenta.observaciones_internas || "",
                incluir_anexos: true,
            };
            this.modalCuentaAbierto = true;
            this.refrescarIconos();
            await this.buscarHonorariosMesPasado(cuenta.cliente_id);
        },

        async abrirModalManual() {
            this.modalCuentaModo = "manual";
            this.cuentaForm = {
                id: null,
                cliente_id: "",
                cliente_nombre: "",
                cliente_documento: "",
                cliente_tipo_persona: "",
                fecha_emision: obtenerFechaHoyISO(),
                valor_digitos: "",
                concepto_honorarios: "",
                observaciones_internas: "",
                incluir_anexos: true,
            };
            this.conceptoMesPasado = null;
            this.modalCuentaAbierto = true;
            if (this.clientes.length === 0) {
                await this.cargarClientes();
            }
            this.refrescarIconos();
        },

        async onSeleccionarClienteManual() {
            if (!this.cuentaForm.cliente_id) {
                this.conceptoMesPasado = null;
                return;
            }
            await this.buscarHonorariosMesPasado(Number(this.cuentaForm.cliente_id));
        },

        async buscarHonorariosMesPasado(clienteId) {
            this.conceptoMesPasado = null;
            this.cargandoMesPasado = true;
            try {
                const periodoPrevio = desplazarPeriodo(this.periodoMes, -1);
                const tableroPrevio = await api.obtenerTablero(periodoPrevio);
                const cuentaPrevia = (tableroPrevio.cuentas_del_mes || []).find(
                    (c) => c.cliente_id === clienteId && c.concepto_honorarios
                );
                if (cuentaPrevia) {
                    this.conceptoMesPasado = cuentaPrevia.concepto_honorarios;
                }
            } catch {
                this.conceptoMesPasado = null;
            } finally {
                this.cargandoMesPasado = false;
            }
        },

        copiarHonorariosMesPasado() {
            if (this.conceptoMesPasado) {
                this.cuentaForm.concepto_honorarios = this.conceptoMesPasado;
                this.notificar("Texto de honorarios del mes anterior copiado.", "info");
            }
        },

        async guardarYGenerarPDF() {
            const valorNum = Number(this.cuentaForm.valor_digitos || 0);
            if (!this.cuentaForm.concepto_honorarios.trim()) {
                this.notificar("Por favor describe el concepto de los honorarios.", "error");
                return;
            }
            if (valorNum <= 0) {
                this.notificar("Ingresa un valor total mayor a $ 0.", "error");
                return;
            }

            this.cargandoAccion = true;
            try {
                let cuentaGuardada;
                if (this.modalCuentaModo === "manual") {
                    if (!this.cuentaForm.cliente_id) {
                        this.notificar("Selecciona un cliente para el cobro.", "error");
                        this.cargandoAccion = false;
                        return;
                    }
                    cuentaGuardada = await api.crearCobroManual({
                        cliente_id: Number(this.cuentaForm.cliente_id),
                        periodo_mes: this.periodoMes,
                        estado: "EMITIDA",
                        fecha_emision: this.cuentaForm.fecha_emision,
                        concepto_honorarios: this.cuentaForm.concepto_honorarios.trim(),
                        valor_total: `${valorNum}.00`,
                        observaciones_internas: this.cuentaForm.observaciones_internas || null,
                    });
                } else {
                    cuentaGuardada = await api.emitirCuenta(this.cuentaForm.id, {
                        fecha_emision: this.cuentaForm.fecha_emision,
                        concepto_honorarios: this.cuentaForm.concepto_honorarios.trim(),
                        valor_total: `${valorNum}.00`,
                        observaciones_internas: this.cuentaForm.observaciones_internas || null,
                    });
                }

                this.modalCuentaAbierto = false;
                this.notificar(
                    `Cuenta ${cuentaGuardada.consecutivo} guardada y PDF generado.`,
                    "success"
                );
                await this.cargarTablero();
                this.verPdfCuenta(
                    cuentaGuardada.id,
                    this.cuentaForm.incluir_anexos,
                    !this.cuentaForm.incluir_anexos
                );
            } catch (err) {
                this.notificar(err.message, "error");
            } finally {
                this.cargandoAccion = false;
            }
        },

        // -------------------------------------------------------------------
        // Directorio de Clientes
        // -------------------------------------------------------------------

        async cargarClientes() {
            try {
                this.clientes = await api.listarClientes({
                    soloActivos: !this.mostrarInactivos,
                    busqueda: this.busquedaClientes,
                });
            } catch (err) {
                this.notificar(err.message, "error");
            } finally {
                this.refrescarIconos();
            }
        },

        abrirModalNuevoCliente() {
            this.clienteEditandoId = null;
            this.clienteForm = {
                tipo_persona: "JURIDICA",
                nombre_razon_social: "",
                documento_nit: "",
                ciudad: "Bogotá D.C.",
                direccion: "",
                correo_contacto: "",
                telefono: "",
                es_recurrente: true,
            };
            this.modalClienteAbierto = true;
            this.refrescarIconos();
        },

        abrirModalEditarCliente(cliente) {
            this.clienteEditandoId = cliente.id;
            this.clienteForm = {
                tipo_persona: cliente.tipo_persona,
                nombre_razon_social: cliente.nombre_razon_social,
                documento_nit: cliente.documento_nit,
                ciudad: cliente.ciudad || "Bogotá D.C.",
                direccion: cliente.direccion || "",
                correo_contacto: cliente.correo_contacto || "",
                telefono: cliente.telefono || "",
                es_recurrente: Boolean(cliente.es_recurrente),
            };
            this.modalClienteAbierto = true;
            this.refrescarIconos();
        },

        async guardarCliente() {
            if (!this.clienteForm.nombre_razon_social.trim() || !this.clienteForm.documento_nit.trim()) {
                this.notificar("El nombre y el documento/NIT son obligatorios.", "error");
                return;
            }
            this.cargandoAccion = true;
            try {
                const payload = {
                    ...this.clienteForm,
                    direccion: this.clienteForm.direccion || null,
                    correo_contacto: this.clienteForm.correo_contacto || null,
                    telefono: this.clienteForm.telefono || null,
                };
                if (this.clienteEditandoId) {
                    await api.actualizarCliente(this.clienteEditandoId, payload);
                    this.notificar("Datos del cliente actualizados.", "success");
                } else {
                    await api.crearCliente(payload);
                    this.notificar("Cliente registrado correctamente.", "success");
                }
                this.modalClienteAbierto = false;
                await this.cargarClientes();
            } catch (err) {
                this.notificar(err.message, "error");
            } finally {
                this.cargandoAccion = false;
            }
        },

        async toggleRecurrenteCliente(cliente) {
            try {
                await api.actualizarCliente(cliente.id, {
                    es_recurrente: !cliente.es_recurrente,
                });
                cliente.es_recurrente = !cliente.es_recurrente;
                this.notificar(
                    cliente.es_recurrente
                        ? `${cliente.nombre_razon_social} marcado como recurrente mensual.`
                        : `${cliente.nombre_razon_social} marcado como esporádico.`,
                    "info"
                );
            } catch (err) {
                this.notificar(err.message, "error");
            }
        },

        async toggleActivoCliente(cliente) {
            try {
                const nuevoEstado = !cliente.activo;
                await api.cambiarEstadoCliente(cliente.id, nuevoEstado);
                this.notificar(
                    nuevoEstado
                        ? `${cliente.nombre_razon_social} reactivado.`
                        : `${cliente.nombre_razon_social} archivado.`,
                    "info"
                );
                await this.cargarClientes();
            } catch (err) {
                this.notificar(err.message, "error");
            }
        },

        // -------------------------------------------------------------------
        // Perfil del Emisor y Documentos Legales
        // -------------------------------------------------------------------

        async cargarEmisor() {
            try {
                this.emisor = await api.obtenerEmisor();
            } catch (err) {
                this.notificar(err.message, "error");
            }
        },

        async guardarEmisor() {
            this.cargandoAccion = true;
            try {
                this.emisor = await api.actualizarEmisor({
                    nombre_completo: this.emisor.nombre_completo,
                    tipo_documento: this.emisor.tipo_documento,
                    numero_documento: this.emisor.numero_documento,
                    rut: this.emisor.rut,
                    direccion: this.emisor.direccion,
                    ciudad: this.emisor.ciudad,
                    telefono: this.emisor.telefono,
                    correo: this.emisor.correo,
                    banco: this.emisor.banco,
                    tipo_cuenta: this.emisor.tipo_cuenta,
                    numero_cuenta: this.emisor.numero_cuenta,
                    nota_legal_iva: this.emisor.nota_legal_iva,
                    nota_retencion: this.emisor.nota_retencion,
                    ruta_firma: this.emisor.ruta_firma,
                    ruta_rut_pdf: this.emisor.ruta_rut_pdf,
                    ruta_cert_bancaria_pdf: this.emisor.ruta_cert_bancaria_pdf,
                });
                this.notificar("Tus datos y notas legales han sido guardados.", "success");
            } catch (err) {
                this.notificar(err.message, "error");
            } finally {
                this.cargandoAccion = false;
            }
        },

        async subirArchivoEmisor(tipo, event) {
            const archivo = event.target.files?.[0];
            if (!archivo) return;

            this.cargandoAccion = true;
            try {
                this.emisor = await api.subirArchivoEmisor(tipo, archivo);
                if (tipo === "firma") {
                    this.firmaCacheBust = Date.now();
                }
                const etiquetas = {
                    firma: "Firma digital",
                    rut: "RUT en PDF",
                    cert_bancaria: "Certificación bancaria",
                };
                this.notificar(`${etiquetas[tipo]} cargada correctamente.`, "success");
            } catch (err) {
                this.notificar(err.message, "error");
            } finally {
                event.target.value = "";
                this.cargandoAccion = false;
                this.refrescarIconos();
            }
        },
    };
};
