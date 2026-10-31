# Urna Digital — demonstração educacional

Aplicação educacional em Python com FastAPI e Uvicorn para demonstrar cadastro
de candidatos, votos cifrados e auditoria de um ledger encadeado e assinado.

No Replit, abra o preview do artifact **Urna Digital** para usar o painel
React/Vite. Ele acessa as rotas do FastAPI pelo prefixo `/api/urna`.

> **Não use este protótipo em eleições oficiais, consultas vinculantes ou
> decisões de alto impacto.** A emissão de tokens não verifica identidade,
> não há garantia de anonimato, resistência à coerção, disponibilidade ou
> segurança operacional, e as chaves privadas ficam no armazenamento local da
> aplicação. Este exemplo não foi submetido a auditoria criptográfica,
> certificação ou revisão jurídica.

## Executar

Na raiz do projeto:

```bash
python -m pip install -r services/urna-digital/requirements.txt
uvicorn app.main:app --app-dir services/urna-digital --host 0.0.0.0 --port 8000 --reload
```

Abra a página inicial para acompanhar o painel visual. Use `/docs` para explorar
e executar as rotas pela documentação interativa.

## Fluxo de demonstração

No painel **Urna Digital**, abra **Iniciar percurso** para receber orientação
pelos quatro passos. O guia não faz alterações ao ser aberto: cada candidatura,
credencial ou voto só é criado quando a pessoa confirma a ação correspondente.
Ao final, o painel atualiza o apuramento e a verificação do ledger.

Também é possível percorrer o fluxo diretamente pela API:

1. Cadastre candidatos em `POST /candidates`.
2. Emita um token descartável em `POST /voters/demo-token`.
3. Envie `candidate_id` e `voter_token` para `POST /votes`.
4. Confira a sequência, a assinatura e os blocos em `GET /audit/ledger`.
5. Consulte os totais de teste em `GET /tally`.

Cada voto recebe uma chave AES-256 única; o conteúdo é cifrado com AES-GCM e
essa chave é protegida pela chave pública RSA-3072. O ledger guarda apenas a
cédula cifrada, encadeia hashes SHA-256 e assina cada bloco com Ed25519. A
chave privada de apuração é necessária para calcular o total.

Os tokens são independentes das cédulas no banco de dados, mas essa separação
não constitui uma garantia de anonimato. O ledger local pode detectar
alterações que não tenham a chave de assinatura, mas não oferece uma âncora
externa contra um administrador com acesso aos arquivos e às chaves.

## Persistência local

O banco SQLite e as chaves são criados em `services/urna-digital/.data/`.
Defina `URNA_DATA_DIR` para escolher outro diretório. Faça backup conjunto
dos dados e das chaves se quiser preservar a demonstração entre reinícios.
Apagar ou perder as chaves impede a apuração dos votos previamente gravados.

## Rotas

| Método | Rota | Uso |
| --- | --- | --- |
| `GET` | `/healthz` | Verificação de disponibilidade |
| `GET` | `/candidates` | Listar candidatos |
| `POST` | `/candidates` | Cadastrar candidato |
| `POST` | `/voters/demo-token` | Emitir token de demonstração |
| `POST` | `/votes` | Cifrar e registrar um voto |
| `GET` | `/crypto/public-key` | Consultar chaves públicas |
| `GET` | `/audit/ledger` | Verificar e listar blocos |
| `GET` | `/tally` | Apurar votos para demonstração |
