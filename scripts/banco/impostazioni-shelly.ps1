# STRUMENTO DI BANCO, NON PER LA CONSEGNA: provato solo su Shelly 1 Gen4, EM Mini Gen4 e Plug M Gen3.
# Dopo un aggiornamento del firmware va lanciato passati i 4 minuti della finestra di configurazione.
#
# Tre impostazioni approvate (1153) su UN solo Shelly per esecuzione:
#   1. rele' al ritorno della corrente: Switch initial_state = restore_last (solo se il dispositivo ha Switch)
#   2. Matter spento: Matter enable = false
#   3. chiamate via Bluetooth spente: BLE rpc.enable = false (il Bluetooth resta acceso)
# Senza -Applica legge soltanto e dice cosa cambierebbe. Non scrive file.
#
# Uso:
#   powershell -ExecutionPolicy Bypass -File .\impostazioni-shelly.ps1 -Url http://<indirizzo-dello-shelly>
#   powershell -ExecutionPolicy Bypass -File .\impostazioni-shelly.ps1 -Url http://<indirizzo-dello-shelly> -Applica
#
# -SpegniBluetooth mette anche BLE enable = false. Rifiuta se il dispositivo ha sensori BLU abbinati (ponte)
# o se il firmware non ha piu' il campo enable (dal 2.0.0 non esiste).
#
# La password della pagina (utente admin) la chiede a schermo, serve solo a calcolare un'impronta e poi viene
# dimenticata. Non compare nell'output.

param(
    [Parameter(Mandatory = $true)][string]$Url,
    [switch]$Applica,
    [switch]$SpegniBluetooth
)

$ErrorActionPreference = "Stop"

# ---- autenticazione digest SHA-256: copiata da censimento-shelly.ps1 senza modifiche ----------------------

function Sha256Hex([string]$testo) {
    $sha = [System.Security.Cryptography.SHA256]::Create()
    try { $byte = $sha.ComputeHash([System.Text.Encoding]::UTF8.GetBytes($testo)) } finally { $sha.Dispose() }
    return -join ($byte | ForEach-Object { $_.ToString("x2") })
}

function RichiestaHttp([string]$url, [string]$autorizzazione) {
    $richiesta = [System.Net.HttpWebRequest]::Create($url)
    $richiesta.Method = "GET"
    $richiesta.Timeout = 8000
    $richiesta.ReadWriteTimeout = 8000
    $richiesta.KeepAlive = $false
    $richiesta.Proxy = $null
    if ($autorizzazione) { $richiesta.Headers["Authorization"] = $autorizzazione }
    try {
        $risposta = $richiesta.GetResponse()
        $lettore = New-Object System.IO.StreamReader($risposta.GetResponseStream())
        $corpo = $lettore.ReadToEnd()
        $lettore.Close(); $risposta.Close()
        return @{ Codice = 200; Corpo = $corpo; Sfida = $null }
    } catch {
        $errore = $_.Exception
        while ($null -ne $errore -and -not ($errore -is [System.Net.WebException])) { $errore = $errore.InnerException }
        if ($null -ne $errore -and $null -ne $errore.Response) {
            $r = $errore.Response
            $codice = [int]$r.StatusCode
            $sfida = $r.Headers["WWW-Authenticate"]
            $corpo = $null
            try { $l = New-Object System.IO.StreamReader($r.GetResponseStream()); $corpo = $l.ReadToEnd(); $l.Close() } catch { }
            $r.Close()
            return @{ Codice = $codice; Corpo = $corpo; Sfida = $sfida }
        }
        return @{ Codice = 0; Corpo = $null; Sfida = $null }
    }
}

$script:Base = $null; $script:Regno = $null; $script:Ha1 = $null; $script:Nonce = $null; $script:Contatore = 0

function Intestazione([string]$percorso) {
    $script:Contatore++
    $nc = "{0:x8}" -f $script:Contatore
    $cnonce = [guid]::NewGuid().ToString("N").Substring(0, 16)
    $ha2 = Sha256Hex ("GET:" + $percorso)
    $risposta = Sha256Hex ($script:Ha1 + ":" + $script:Nonce + ":" + $nc + ":" + $cnonce + ":auth:" + $ha2)
    return ('Digest username="admin", realm="' + $script:Regno + '", nonce="' + $script:Nonce + '", uri="' + $percorso +
            '", cnonce="' + $cnonce + '", nc=' + $nc + ', qop=auth, response="' + $risposta + '", algorithm=SHA-256')
}

function Chiama([string]$metodoConQuery) {
    $percorso = "/rpc/" + $metodoConQuery
    $url = $script:Base + $percorso
    $esito = $null
    for ($tentativo = 0; $tentativo -lt 2; $tentativo++) {
        $autorizzazione = $null
        if ($script:Ha1 -and $script:Nonce) { $autorizzazione = Intestazione $percorso }
        $esito = RichiestaHttp $url $autorizzazione
        if ($esito.Codice -eq 200) {
            try { return [pscustomobject]@{ Ok = $true; Codice = 200; Dati = ($esito.Corpo | ConvertFrom-Json); Errore = $null } }
            catch { return [pscustomobject]@{ Ok = $false; Codice = 200; Dati = $null; Errore = "risposta non JSON" } }
        }
        if ($esito.Codice -eq 401 -and $script:Ha1 -and $esito.Sfida -and ($esito.Sfida -match 'nonce="([^"]+)"')) {
            $script:Nonce = $Matches[1]; $script:Contatore = 0
            continue
        }
        break
    }
    return [pscustomobject]@{ Ok = $false; Codice = $esito.Codice; Dati = $null; Errore = $esito.Corpo }
}

function Valore($oggetto, [string]$nome) {
    if ($null -eq $oggetto) { return $null }
    $p = $oggetto.PSObject.Properties[$nome]
    if ($null -eq $p) { return $null }
    return $p.Value
}

# ---- parti nuove --------------------------------------------------------------------------------------------

# Chiamata di scrittura con la configurazione in JSON nella query. Il percorso passa prima da [Uri], cosi' l'uri
# della firma digest e' identico a quello che .NET manda davvero.
function ChiamaConConfig([string]$metodo, [string]$prefisso, [string]$configJson) {
    $grezzo = "/rpc/" + $metodo + "?" + $prefisso + "config=" + [Uri]::EscapeDataString($configJson)
    $normale = ([Uri]("http://x" + $grezzo)).PathAndQuery
    return Chiama ($normale.Substring(5))
}

function Testo($v) {
    if ($null -eq $v) { return "(assente)" }
    if ($v -is [bool]) { if ($v) { return "true" } else { return "false" } }
    return [string]$v
}

function Rele($v) {
    if ($null -eq $v) { return "sconosciuto" }
    if ($v) { return "acceso" } else { return "spento" }
}

# Legge le impostazioni che interessano. Switch e' $null se il dispositivo non ha il componente.
function Leggi {
    $sw = Chiama "Switch.GetConfig?id=0"
    $st = $null
    if ($sw.Ok) { $st = Chiama "Switch.GetStatus?id=0" }
    $ma = Chiama "Matter.GetConfig"
    $bl = Chiama "BLE.GetConfig"
    $haEnable = $bl.Ok -and ($null -ne $bl.Dati.PSObject.Properties["enable"])
    return [pscustomobject]@{
        HaSwitch     = $sw.Ok
        InitialState = $(if ($sw.Ok) { Valore $sw.Dati "initial_state" } else { $null })
        Output       = $(if ($null -ne $st -and $st.Ok) { Valore $st.Dati "output" } else { $null })
        MatterOk     = $ma.Ok
        Matter       = $(if ($ma.Ok) { Valore $ma.Dati "enable" } else { $null })
        BleOk        = $bl.Ok
        BleRpc       = $(if ($bl.Ok) { Valore (Valore $bl.Dati "rpc") "enable" } else { $null })
        HaBleEnable  = $haEnable
        BleEnable    = $(if ($haEnable) { Valore $bl.Dati "enable" } else { $null })
    }
}

# ---- 1. identita' e password ---------------------------------------------------------------------------------

$script:Base = $Url.Trim().TrimEnd("/")
$info = RichiestaHttp ($script:Base + "/rpc/Shelly.GetDeviceInfo") $null
if ($info.Codice -ne 200) {
    Write-Host "Il dispositivo non risponde (codice $($info.Codice)). Mi fermo." -ForegroundColor Red
    exit 1
}
$dispositivo = $info.Corpo | ConvertFrom-Json
Write-Host ""
Write-Host ("=== {0}   modello {1} ({2})   firmware {3} ===" -f $dispositivo.id, $dispositivo.model, $dispositivo.app, $dispositivo.ver) -ForegroundColor Cyan

if ($dispositivo.auth_en) {
    $script:Regno = if ($dispositivo.auth_domain) { $dispositivo.auth_domain } else { $dispositivo.id }
    $sicura = Read-Host ("Password della pagina di " + $dispositivo.id + " (utente admin)") -AsSecureString
    $ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($sicura)
    try { $chiara = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr) }
    finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr) }
    $script:Ha1 = Sha256Hex ("admin:" + $script:Regno + ":" + $chiara)
    $chiara = $null; $sicura = $null
    $prova = Chiama "Sys.GetStatus"
    if (-not $prova.Ok) {
        Write-Host "Password rifiutata o nessuna risposta (codice $($prova.Codice)). Mi fermo." -ForegroundColor Red
        exit 1
    }
}

# ---- 2. il prima ---------------------------------------------------------------------------------------------

$prima = Leggi
if (-not $prima.MatterOk) { Write-Host "Matter.GetConfig non risponde: Matter resta com'e'." -ForegroundColor Yellow }
if (-not $prima.BleOk) { Write-Host "BLE.GetConfig non risponde: Bluetooth resta com'e'." -ForegroundColor Yellow }

# controlli di -SpegniBluetooth, prima di qualunque scrittura
if ($SpegniBluetooth) {
    if (-not $prima.HaBleEnable) {
        Write-Host "RIFIUTO -SpegniBluetooth: questo firmware non ha il campo BLE enable (dal 2.0.0 non esiste piu'). Nessuna modifica." -ForegroundColor Red
        exit 1
    }
    $comp = Chiama "Shelly.GetComponents?dynamic_only=true"
    if (-not $comp.Ok) {
        Write-Host "RIFIUTO -SpegniBluetooth: non riesco a leggere i componenti abbinati. Nessuna modifica." -ForegroundColor Red
        exit 1
    }
    $abbinati = @(@(Valore $comp.Dati "components") | Where-Object { $null -ne $_ -and $_.key -match '^(bthome|blu)' })
    if ($abbinati.Count -gt 0) {
        Write-Host ("RIFIUTO -SpegniBluetooth: il dispositivo fa da ponte ({0} componenti BLU: {1}). Nessuna modifica." -f $abbinati.Count, (($abbinati | ForEach-Object { $_.key }) -join ", ")) -ForegroundColor Red
        exit 1
    }
}

# ---- piano delle modifiche -----------------------------------------------------------------------------------

$piano = @()
if ($prima.HaSwitch) {
    $piano += [pscustomobject]@{ Nome = "Rele' al ritorno corrente (initial_state)"; Chiave = "InitialState"; Previsto = "restore_last" }
}
if ($prima.MatterOk) {
    $piano += [pscustomobject]@{ Nome = "Matter (enable)"; Chiave = "Matter"; Previsto = "false" }
}
if ($prima.BleOk) {
    $piano += [pscustomobject]@{ Nome = "Chiamate via Bluetooth (rpc.enable)"; Chiave = "BleRpc"; Previsto = "false" }
    if ($prima.HaBleEnable) {
        $prev = if ($SpegniBluetooth) { "false" } else { Testo $prima.BleEnable }
        $piano += [pscustomobject]@{ Nome = "Bluetooth (enable)"; Chiave = "BleEnable"; Previsto = $prev }
    }
}

Write-Host ""
Write-Host "Valore attuale -> valore previsto:"
$piano | ForEach-Object {
    $att = Testo ($prima.($_.Chiave))
    [pscustomobject]@{ Impostazione = $_.Nome; Attuale = $att; Previsto = $_.Previsto; Cambia = $(if ($att -eq $_.Previsto) { "no" } else { "SI'" }) }
} | Format-Table -AutoSize | Out-String | Write-Host
if (-not $prima.HaSwitch) { Write-Host "Nessun componente Switch: niente rele' su questo dispositivo." }
else { Write-Host ("Rele' adesso: " + (Rele $prima.Output)) }

if (-not $Applica) {
    Write-Host ""
    Write-Host "Sola lettura: nessuna modifica. Per applicare, rilancia con -Applica." -ForegroundColor Green
    exit 0
}

# ---- 4. scritture, una alla volta: Switch, Matter, BLE --------------------------------------------------------

$serveRiavvio = $false
$fermato = $false
$risultati = @{}

function Manda([string]$nome, [string]$metodo, [string]$prefisso, [string]$config) {
    Write-Host ("-> {0}  {1}" -f $metodo, $config)
    $r = ChiamaConConfig $metodo $prefisso $config
    if (-not $r.Ok) {
        Write-Host ("   ERRORE (codice {0}): {1}" -f $r.Codice, $r.Errore) -ForegroundColor Red
        return $false
    }
    $rr = Valore $r.Dati "restart_required"
    Write-Host ("   risposta: {0}   restart_required = {1}" -f ($r.Dati | ConvertTo-Json -Compress -Depth 5), (Testo $rr))
    if ($rr -eq $true) { $script:serveRiavvio = $true }
    return $true
}

Write-Host ""
if ($prima.HaSwitch -and (Testo $prima.InitialState) -ne "restore_last") {
    if (-not (Manda "Switch" "Switch.SetConfig" "id=0&" '{"initial_state":"restore_last"}')) { $fermato = $true }
}
if (-not $fermato -and $prima.MatterOk -and (Testo $prima.Matter) -ne "false") {
    if (-not (Manda "Matter" "Matter.SetConfig" "" '{"enable":false}')) { $fermato = $true }
}
if (-not $fermato -and $prima.BleOk) {
    $parti = @()
    if ($SpegniBluetooth -and (Testo $prima.BleEnable) -ne "false") { $parti += '"enable":false' }
    if ((Testo $prima.BleRpc) -ne "false") { $parti += '"rpc":{"enable":false}' }
    if ($parti.Count -gt 0) {
        if (-not (Manda "BLE" "BLE.SetConfig" "" ("{" + ($parti -join ",") + "}"))) { $fermato = $true }
    }
}
if ($fermato) { Write-Host "Mi fermo: le chiamate successive non sono state mandate." -ForegroundColor Red }

# ---- 5. riavvio, solo se richiesto e confermato ---------------------------------------------------------------

$riavviato = $false
if ($serveRiavvio) {
    Write-Host ""
    $si = Read-Host "Il dispositivo chiede un riavvio. Riavvio adesso? s/n"
    if ($si -match '^[sS]') {
        $uptimePrima = Valore (Chiama "Sys.GetStatus").Dati "uptime"
        $rb = Chiama "Shelly.Reboot"
        if (-not $rb.Ok) {
            Write-Host ("Shelly.Reboot rifiutato (codice {0}): {1}" -f $rb.Codice, $rb.Errore) -ForegroundColor Red
        } else {
            Write-Host "Riavvio mandato, aspetto che risponda (al massimo 90 s)..."
            $inizio = Get-Date
            Start-Sleep -Seconds 3
            while (((Get-Date) - $inizio).TotalSeconds -lt 90) {
                $p = RichiestaHttp ($script:Base + "/rpc/Shelly.GetDeviceInfo") $null
                if ($p.Codice -eq 200) {
                    $up = Valore (Chiama "Sys.GetStatus").Dati "uptime"
                    if ($null -eq $uptimePrima -or ($null -ne $up -and $up -lt $uptimePrima)) { $riavviato = $true; break }
                }
                Start-Sleep -Seconds 2
            }
            if ($riavviato) { Write-Host ("Di nuovo in linea dopo {0:N0} s." -f ((Get-Date) - $inizio).TotalSeconds) -ForegroundColor Green }
            else { Write-Host "Dopo 90 s non risulta riavviato: controlla nell'app. Leggo comunque il dopo." -ForegroundColor Yellow }
        }
    } else {
        Write-Host "Riavvio non fatto: le impostazioni con restart_required valgono solo dopo un riavvio." -ForegroundColor Yellow
    }
}

# ---- 6-7. il dopo e la tabella finale -------------------------------------------------------------------------

$dopo = Leggi
Write-Host ""
Write-Host ("Esito per Massimiliano: {0} ({1}, firmware {2})" -f $dispositivo.id, $dispositivo.model, $dispositivo.ver) -ForegroundColor Cyan
$piano | ForEach-Object {
    $p = Testo ($prima.($_.Chiave)); $d = Testo ($dopo.($_.Chiave))
    $esito = if ($p -eq $_.Previsto -and $d -eq $_.Previsto) { "gia' a posto" }
             elseif ($d -eq $_.Previsto) { "cambiata" }
             elseif ($serveRiavvio -and -not $riavviato) { "NON ancora (manca il riavvio?)" }
             else { "NON riuscita" }
    [pscustomobject]@{ Impostazione = $_.Nome; Prima = $p; Dopo = $d; Esito = $esito }
} | Format-Table -AutoSize | Out-String | Write-Host

if ($prima.HaSwitch) {
    $stesso = if ($null -ne $prima.Output -and $prima.Output -eq $dopo.Output) { "stesso stato" } else { "STATO DIVERSO o sconosciuto" }
    $quando = if ($riavviato) { "prima del riavvio" } else { "prima delle modifiche (nessun riavvio)" }
    Write-Host ("Rele': {0} {1}, adesso {2} -> {3}" -f $quando, (Rele $prima.Output), (Rele $dopo.Output), $stesso)
} else {
    Write-Host "Rele': nessuno su questo dispositivo."
}
Write-Host ("Riavvio: " + $(if ($riavviato) { "fatto" } elseif ($serveRiavvio) { "richiesto ma non fatto" } else { "non richiesto" }))
$script:Ha1 = $null
