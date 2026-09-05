"""Administración de dispositivos, alias y credenciales de ingesta."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from api_client import ApiError
from services import get_api_client

st.write(
    "Registre cada ESP32 antes de enviar datos, asígnele un alias y emita una "
    "credencial identificable para saber quién insertó cada muestra."
)
st.warning(
    "Use estas operaciones únicamente por HTTPS. El secret key se entrega una sola "
    "vez y la API no puede recuperarlo después."
)

auth = st.container(horizontal=True)
admin_api_key = auth.text_input("Admin API key", type="password")
admin_secret_key = auth.text_input("Admin secret key", type="password")
if not admin_api_key or not admin_secret_key:
    st.info("Ingrese las credenciales administrativas configuradas en el servidor.")
    st.stop()

client = get_api_client(st.session_state.api_base_url)
try:
    devices = client.list_managed_devices(
        admin_api_key=admin_api_key,
        admin_secret_key=admin_secret_key,
    )
    credentials = client.list_device_credentials(
        admin_api_key=admin_api_key,
        admin_secret_key=admin_secret_key,
    )
except ApiError as exc:
    st.error(str(exc))
    st.stop()

register_tab, credentials_tab = st.tabs(["Dispositivos", "Credenciales"])

with register_tab:
    st.subheader("Registrar dispositivo")
    with st.form("admin_register_device"):
        row = st.container(horizontal=True)
        new_group = row.text_input("Grupo", value="grupo-01")
        new_device = row.text_input("ID del dispositivo", value="esp32-grupo-01")
        new_alias = row.text_input("Alias", value="Invernadero principal")
        register = st.form_submit_button("Registrar", type="primary")
    if register:
        try:
            client.register_device(
                group_id=new_group,
                device_id=new_device,
                alias=new_alias,
                admin_api_key=admin_api_key,
                admin_secret_key=admin_secret_key,
            )
        except ApiError as exc:
            st.error(str(exc))
        else:
            st.success("Dispositivo registrado con sus sensores base.")
            st.rerun()

    if devices:
        st.dataframe(pd.DataFrame(devices), width="stretch", hide_index=True)
        device_ids = [str(item["device_id"]) for item in devices]

        st.subheader("Cambiar alias")
        with st.form("admin_device_alias"):
            alias_device = st.selectbox("Dispositivo", device_ids, key="alias_device")
            alias_value = st.text_input("Nuevo alias")
            update_alias = st.form_submit_button("Actualizar alias")
        if update_alias:
            try:
                client.update_device_alias(
                    alias_device,
                    alias_value,
                    admin_api_key=admin_api_key,
                    admin_secret_key=admin_secret_key,
                )
            except ApiError as exc:
                st.error(str(exc))
            else:
                st.success("Alias actualizado. Las muestras anteriores conservan su snapshot.")
                st.rerun()

        st.subheader("Activar o desactivar")
        action_row = st.container(horizontal=True)
        status_device = action_row.selectbox(
            "Dispositivo administrado", device_ids, key="status_device"
        )
        if action_row.button("Activar", key="activate_device"):
            try:
                client.set_device_active(
                    status_device,
                    True,
                    admin_api_key=admin_api_key,
                    admin_secret_key=admin_secret_key,
                )
            except ApiError as exc:
                st.error(str(exc))
            else:
                st.rerun()
        if action_row.button("Desactivar", key="deactivate_device"):
            try:
                client.set_device_active(
                    status_device,
                    False,
                    admin_api_key=admin_api_key,
                    admin_secret_key=admin_secret_key,
                )
            except ApiError as exc:
                st.error(str(exc))
            else:
                st.rerun()
    else:
        st.info("Todavía no hay dispositivos administrados.")

with credentials_tab:
    st.subheader("Emitir credencial")
    device_ids = [str(item["device_id"]) for item in devices]
    if not device_ids:
        st.info("Registre primero un dispositivo.")
    else:
        with st.form("admin_create_credential"):
            credential_device = st.selectbox(
                "Dispositivo vinculado", device_ids, key="credential_device"
            )
            credential_alias = st.text_input(
                "Alias de quien inserta",
                value="ESP32 invernadero principal",
                help="Este texto quedará guardado en cada muestra.",
            )
            create_credential = st.form_submit_button(
                "Generar API key y secret", type="primary"
            )
        if create_credential:
            try:
                issued = client.create_device_credential(
                    device_id=credential_device,
                    alias=credential_alias,
                    admin_api_key=admin_api_key,
                    admin_secret_key=admin_secret_key,
                )
            except ApiError as exc:
                st.error(str(exc))
            else:
                st.session_state["issued_device_credential"] = issued

    issued = st.session_state.get("issued_device_credential")
    if issued:
        st.error("Copie estas dos claves ahora. El secret no volverá a mostrarse.")
        st.code(f"X-API-Key: {issued['api_key']}\nX-Secret-Key: {issued['secret_key']}")
        if st.button("Ya guardé las claves; ocultarlas"):
            del st.session_state["issued_device_credential"]
            st.rerun()

    if credentials:
        st.dataframe(pd.DataFrame(credentials), width="stretch", hide_index=True)
        active_credentials = [item for item in credentials if item.get("active")]
        if active_credentials:
            labels = {
                f"{item['alias']} · {item['device_id']} · {item['api_key_prefix']}…": str(item["id"])
                for item in active_credentials
            }
            selected = st.selectbox("Credencial activa", list(labels), key="revoke_credential")
            if st.button("Revocar credencial", type="secondary"):
                try:
                    client.revoke_device_credential(
                        labels[selected],
                        admin_api_key=admin_api_key,
                        admin_secret_key=admin_secret_key,
                    )
                except ApiError as exc:
                    st.error(str(exc))
                else:
                    st.session_state.pop("issued_device_credential", None)
                    st.rerun()
    else:
        st.info("Todavía no se han emitido credenciales.")
