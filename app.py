import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from geopy.geocoders import Nominatim
from geopy.distance import geodesic
import time

# --- CONFIGURAÇÃO ---
st.set_page_config(page_title="DCP-RECON Pro", page_icon="🚀")
st.title("🚀 DCP-RECON: Automação Total")

def conectar_google():
    scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds_dict = st.secrets["gcp_service_account"].to_dict()
    creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")
    creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
    return gspread.authorize(creds)

# --- CONFIGURAÇÃO DE NOMES ---
NOME_PLANILHA_RESPOSTAS = "DCP_Respostas"
NOME_PLANILHA_GRUPOS = "DCP_Grupos"
NOME_PLANILHA_DESTINO = "DCP_CADASTRO_GERAL"

try:
    gc = conectar_google()
    
    # 1. Carrega Respostas
    sh_respostas = gc.open(NOME_PLANILHA_RESPOSTAS)
    wks_respostas = sh_respostas.sheet1
    df_respostas = pd.DataFrame(wks_respostas.get_all_records())

    if not df_respostas.empty:
        if 'Status' not in df_respostas.columns:
            st.error("Erro: A coluna 'Status' não foi encontrada na planilha de Respostas.")
            st.stop()
        
        pendentes = df_respostas[df_respostas['Status'].astype(str).str.strip() == ""]

        if not pendentes.empty:
            st.subheader("📋 Selecione o Candidato")
            lista_nomes = pendentes['Nome Completo'].tolist()
            nome_selecionado = st.selectbox("Quem deseja processar?", lista_nomes)
            
            # Localiza índice da linha original
            idx_original = df_respostas[df_respostas['Nome Completo'] == nome_selecionado].index[0] + 2
            cand = pendentes[pendentes['Nome Completo'] == nome_selecionado].iloc[0]

            if st.button("🔍 CALCULAR MELHOR OPÇÃO"):
                sh_grupos = gc.open(NOME_PLANILHA_GRUPOS)
                df_grupos = pd.DataFrame(sh_grupos.sheet1.get_all_records())
                
                geolocator = Nominatim(user_agent="dcp_v5_auto")
                loc_cand = geolocator.geocode(cand['Endereço Completo'])
                
                if loc_cand:
                    ponto_cand = (loc_cand.latitude, loc_cand.longitude)
                    sugestoes = []

                    for _, g in df_grupos.iterrows():
                        if int(g['Membros Atuais']) < int(g['Capacidade Máxima']):
                            # Filtro de Perfil
                            p_c = str(cand['Perfil']).strip()
                            p_g = str(g['Perfil']).strip()
                            if p_c == p_g or p_g == "Misto":
                                loc_g = geolocator.geocode(g['Endereço'])
                                if loc_g:
                                    dist = geodesic(ponto_cand, (loc_g.latitude, loc_g.longitude)).km
                                    if dist <= raio_km:
                                        sugestoes.append({"Grupo": g['Nome do Grupo'], "Dist": dist, "Lider": g['Líder']})
                                time.sleep(0.5)

                    if sugestoes:
                        melhor = sorted(sugestoes, key=lambda x: x['Dist'])[0]
                        st.session_state['resultado'] = melhor
                        st.success(f"🎯 Sugestão: {melhor['Grupo']} (a {melhor['Dist']:.2f} km)")
                    else:
                        st.warning("Nenhum grupo compatível no raio definido.")
                else:
                    st.error("Endereço do candidato não localizado.")

            # --- BOTÃO DE CONFIRMAÇÃO ---
            if 'resultado' in st.session_state:
                res = st.session_state['resultado']
                if st.button(f"✅ CONFIRMAR ENTRADA NO GRUPO: {res['Grupo']}"):
                    with st.spinner("Registrando nos sistemas..."):
                        # A. Abre Planilha de Destino
                        sh_dest = gc.open(NOME_PLANILHA_DESTINO)
                        
                        try:
                            # Tenta abrir a aba do grupo, se não existir, cria uma nova
                            try:
                                wks_dest = sh_dest.worksheet(res['Grupo'])
                            except gspread.exceptions.WorksheetNotFound:
                                wks_dest = sh_dest.add_worksheet(title=res['Grupo'], rows="100", cols="10")
                                wks_dest.append_row(["Data Registro", "Nome", "Endereço", "Perfil"])
                            
                            # B. Adiciona o Candidato na aba do grupo
                            data_hoje = time.strftime("%d/%m/%Y")
                            wks_dest.append_row([data_hoje, cand['Nome Completo'], cand['Endereço Completo'], cand['Perfil']])
                            
                            # C. Marca Status como OK na planilha de entrada
                            col_status = df_respostas.columns.get_loc('Status') + 1
                            wks_respostas.update_cell(idx_original, col_status, "OK")
                            
                            st.balloons()
                            st.success(f"Sucesso! {nome_selecionado} registrado em '{res['Grupo']}'.")
                            del st.session_state['resultado']
                            time.sleep(2)
                            st.rerun()
                        except Exception as e_dest:
                            st.error(f"Erro ao salvar na aba: {e_dest}")
        else:
            st.info("✅ Tudo limpo! Não há candidatos pendentes.")
    else:
        st.warning("A planilha de respostas está vazia.")

except Exception as e:
    st.error(f"Erro Geral: {e}")
