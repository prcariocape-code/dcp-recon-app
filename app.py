import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from geopy.geocoders import Nominatim
from geopy.distance import geodesic
import time

# --- CONFIGURAÇÃO DA PÁGINA ---
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

# --- INTERFACE LATERAL ---
st.sidebar.header("Configurações de Busca")
raio_selecionado = st.sidebar.slider("Raio de Busca (KM)", 1, 50, 15)

try:
    gc = conectar_google()
    
    # 1. Carrega Respostas
    sh_respostas = gc.open(NOME_PLANILHA_RESPOSTAS)
    wks_respostas = sh_respostas.sheet1
    df_respostas = pd.DataFrame(wks_respostas.get_all_records())

    if not df_respostas.empty:
        if 'Status' not in df_respostas.columns:
            st.error("Erro: A coluna 'Status' não existe em DCP_Respostas.")
            st.stop()
        
        pendentes = df_respostas[df_respostas['Status'].astype(str).str.strip() == ""]

        if not pendentes.empty:
            st.subheader("📋 Selecione o Candidato")
            lista_nomes = pendentes['Nome Completo'].tolist()
            nome_selecionado = st.selectbox("Quem deseja processar?", lista_nomes)
            
            idx_original = df_respostas[df_respostas['Nome Completo'] == nome_selecionado].index[0] + 2
            cand = pendentes[pendentes['Nome Completo'] == nome_selecionado].iloc[0]

            if st.button("🔍 CALCULAR MELHOR OPÇÃO"):
                sh_grupos = gc.open(NOME_PLANILHA_GRUPOS)
                wks_grupos_aba = sh_grupos.sheet1
                df_grupos = pd.DataFrame(wks_grupos_aba.get_all_records())
                
                geolocator = Nominatim(user_agent="dcp_v7_final")
                loc_cand = geolocator.geocode(cand['Endereço Completo'])
                
                if loc_cand:
                    ponto_cand = (loc_cand.latitude, loc_cand.longitude)
                    sugestoes = []

                    for i, g in df_grupos.iterrows():
                        if int(g['Membros Atuais']) < int(g['Capacidade Máxima']):
                            p_c = str(cand['Perfil']).strip()
                            p_g = str(g['Perfil']).strip()
                            
                            if p_c == p_g or p_g == "Misto":
                                loc_g = geolocator.geocode(g['Endereço'])
                                if loc_g:
                                    dist = geodesic(ponto_cand, (loc_g.latitude, loc_g.longitude)).km
                                    if dist <= raio_selecionado:
                                        sugestoes.append({
                                            "Grupo": g['Nome do Grupo'], 
                                            "Dist": dist, 
                                            "Lider": g['Líder'],
                                            "Linha_Grupo": i + 2,
                                            "Membros_Atuais": int(g['Membros Atuais']),
                                            "Col_Membros": df_grupos.columns.get_loc('Membros Atuais') + 1
                                        })
                                time.sleep(0.5)

                    if sugestoes:
                        melhor = sorted(sugestoes, key=lambda x: x['Dist'])[0]
                        st.session_state['resultado'] = melhor
                        st.success(f"🎯 Sugestão: {melhor['Grupo']} (a {melhor['Dist']:.2f} km)")
                    else:
                        st.warning(f"Nenhum grupo compatível num raio de {raio_selecionado}km.")
                else:
                    st.error("Endereço do candidato não localizado.")

            if 'resultado' in st.session_state:
                res = st.session_state['resultado']
                if st.button(f"✅ CONFIRMAR EM: {res['Grupo']}"):
                    with st.spinner("Registrando..."):
                        try:
                            # A. Cadastro Geral
                            sh_dest = gc.open(NOME_PLANILHA_DESTINO)
                            try:
                                wks_dest = sh_dest.worksheet(res['Grupo'])
                            except:
                                wks_dest = sh_dest.add_worksheet(title=res['Grupo'], rows="100", cols="5")
                                wks_dest.append_row(["Data", "Nome", "Endereço", "Perfil"])
                            
                            wks_dest.append_row([time.strftime("%d/%m/%Y"), cand['Nome Completo'], cand['Endereço Completo'], cand['Perfil']])
                            
                            # B. Marcar Status OK
                            col_status = df_respostas.columns.get_loc('Status') + 1
                            wks_respostas.update_cell(idx_original, col_status, "OK")
                            
                            # C. Atualizar Vagas
                            sh_grupos = gc.open(NOME_PLANILHA_GRUPOS)
                            wks_g = sh_grupos.sheet1
                            wks_g.update_cell(res['Linha_Grupo'], res['Col_Membros'], res['Membros_Atuais'] + 1)
                            
                            st.balloons()
                            st.success("Candidato alocado com sucesso!")
                            del st.session_state['resultado']
                            time.sleep(1)
                            st.rerun()
                        except Exception as e:
                            # Se o erro for o tal '200', a gente ignora e finge que deu certo (porque deu!)
                            if "200" in str(e):
                                st.rerun()
                            else:
                                st.error(f"Erro no registro: {e}")
        else:
            st.info("✅ Tudo processado!")
    else:
        st.warning("Planilha vazia.")

except Exception as e:
    if "200" not in str(e):
        st.error(f"Erro Geral: {e}")
    else:
        st.rerun()
