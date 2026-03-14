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
            st.error("Erro: A coluna 'Status' não existe em DCP_Respostas. Crie-a na primeira linha.")
            st.stop()
        
        # Filtra pendentes
        pendentes = df_respostas[df_respostas['Status'].astype(str).str.strip() == ""]

        if not pendentes.empty:
            st.subheader("📋 Selecione o Candidato")
            lista_nomes = pendentes['Nome Completo'].tolist()
            nome_selecionado = st.selectbox("Quem deseja processar?", lista_nomes)
            
            # Dados do candidato escolhido
            idx_original = df_respostas[df_respostas['Nome Completo'] == nome_selecionado].index[0] + 2
            cand = pendentes[pendentes['Nome Completo'] == nome_selecionado].iloc[0]

            if st.button("🔍 CALCULAR MELHOR OPÇÃO"):
                sh_grupos = gc.open(NOME_PLANILHA_GRUPOS)
                wks_grupos_aba = sh_grupos.sheet1
                df_grupos = pd.DataFrame(wks_grupos_aba.get_all_records())
                
                geolocator = Nominatim(user_agent="dcp_v6_final")
                loc_cand = geolocator.geocode(cand['Endereço Completo'])
                
                if loc_cand:
                    ponto_cand = (loc_cand.latitude, loc_cand.longitude)
                    sugestoes = []

                    for i, g in df_grupos.iterrows():
                        # Verifica capacidade
                        if int(g['Membros Atuais']) < int(g['Capacidade Máxima']):
                            # Filtro de Perfil
                            p_c = str(cand['Perfil']).strip()
                            p_g = str(g['Perfil']).strip()
                            
                            if p_c == p_g or p_g == "Misto":
                                loc_g = geolocator.geocode(g['Endereço'])
                                if loc_g:
                                    dist = geodesic(ponto_cand, (loc_g.latitude, loc_g.longitude)).km
                                    if dist <= raio_selecionado:
                                        # Guardamos o índice da linha do grupo para atualizar depois
                                        sugestoes.append({
                                            "Grupo": g['Nome do Grupo'], 
                                            "Dist": dist, 
                                            "Lider": g['Líder'],
                                            "Linha_Grupo": i + 2,
                                            "Membros_Atuais": int(g['Membros Atuais'])
                                        })
                                time.sleep(0.5)

                    if sugestoes:
                        melhor = sorted(sugestoes, key=lambda x: x['Dist'])[0]
                        st.session_state['resultado'] = melhor
                        st.success(f"🎯 Sugestão: {melhor['Grupo']} (a {melhor['Dist']:.2f} km)")
                    else:
                        st.warning(f"Nenhum grupo compatível num raio de {raio_selecionado}km.")
                else:
                    st.error("Endereço do candidato não localizado pelo GPS.")

            # --- BOTÃO DE CONFIRMAÇÃO ---
            if 'resultado' in st.session_state:
                res = st.session_state['resultado']
                if st.button(f"✅ CONFIRMAR ENTRADA EM: {res['Grupo']}"):
                    with st.spinner("Registrando e atualizando vagas..."):
                        sh_dest = gc.open(NOME_PLANILHA_DESTINO)
                        
                        try:
                            # 1. Adiciona na aba do grupo no Cadastro Geral
                            try:
                                wks_dest = sh_dest.worksheet(res['Grupo'])
                            except gspread.exceptions.WorksheetNotFound:
                                wks_dest = sh_dest.add_worksheet(title=res['Grupo'], rows="100", cols="5")
                                wks_dest.append_row(["Data", "Nome", "Endereço", "Perfil"])
                            
                            wks_dest.append_row([time.strftime("%d/%m/%Y"), cand['Nome Completo'], cand['Endereço Completo'], cand['Perfil']])
                            
                            # 2. Marca OK na planilha de entrada
                            col_status = df_respostas.columns.get_loc('Status') + 1
                            wks_respostas.update_cell(idx_original, col_status, "OK")
                            
                            # 3. Atualiza Membros Atuais na DCP_Grupos (+1)
                            sh_grupos = gc.open(NOME_PLANILHA_GRUPOS)
                            wks_g = sh_grupos.sheet1
                            # A coluna Membros Atuais costuma ser a 4ª, mas vamos garantir pelo nome
                            col_membros = df_grupos.columns.get_loc('Membros Atuais') + 1
                            wks_g.update_cell(res['Linha_Grupo'], col_membros, res['Membros_Atuais'] + 1)
                            
                            st.balloons()
                            st.success(f"Tudo Pronto! {nome_selecionado} alocado.")
                            del st.session_state['resultado']
                            time.sleep(2)
                            st.rerun()
                        except Exception as e_dest:
                            st.error(f"Erro no registro: {e_dest}")
        else:
            st.info("✅ Todos os candidatos processados!")
    else:
        st.warning("A planilha de respostas está vazia.")

except Exception as e:
    st.error(f"Erro Geral: {e}")
