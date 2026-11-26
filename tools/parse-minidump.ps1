param([string]$DumpPath)
# Minimal Windows minidump reader: exception record, modules, faulting-thread stack profile.
# No WinDbg needed. Usage: powershell -NoProfile -File parse-minidump.ps1 <path-to.dmp>
$bytes = [System.IO.File]::ReadAllBytes($DumpPath)
function u32([int]$o) { return [System.BitConverter]::ToUInt32($bytes, $o) }
function u64([int]$o) { return [System.BitConverter]::ToUInt64($bytes, $o) }
function wstr([long]$rva) {
    $len = u32 ([int]$rva)
    return [System.Text.Encoding]::Unicode.GetString($bytes, ([int]$rva) + 4, $len)
}
if ([System.Text.Encoding]::ASCII.GetString($bytes, 0, 4) -ne 'MDMP') { Write-Output 'NOT A MINIDUMP'; exit 1 }
$numStreams = u32 8; $dirRva = u32 12
Write-Output ("streams: {0}  file: {1} bytes  created: {2}" -f $numStreams, $bytes.Length, (Get-Item $DumpPath).CreationTime)
$streams = @{}
for ($i = 0; $i -lt $numStreams; $i++) {
    $b = $dirRva + $i * 12
    $streams[[int](u32 $b)] = @{ Size = (u32 ($b + 4)); Rva = (u32 ($b + 8)) }
}
# --- modules (type 4) ---
$mods = @()
if ($streams.ContainsKey(4)) {
    $r = $streams[4].Rva; $n = u32 $r
    for ($i = 0; $i -lt $n; $i++) {
        $e = $r + 4 + $i * 108
        $mods += [pscustomobject]@{ Base = (u64 $e); Size = (u32 ($e + 8)); Name = (wstr (u32 ($e + 20))) }
    }
}
function Find-Module([uint64]$addr) {
    foreach ($m in $mods) { if ($addr -ge $m.Base -and $addr -lt ($m.Base + $m.Size)) { return $m } }
    return $null
}
# --- exception (type 6) ---
if ($streams.ContainsKey(6)) {
    $r = $streams[6].Rva
    $tid = u32 $r; $code = u32 ($r + 8); $addr = u64 ($r + 24); $nparams = u32 ($r + 32)
    $fm = Find-Module $addr
    Write-Output ("EXCEPTION code=0x{0:X8} address=0x{1:X} thread={2} params={3}" -f $code, $addr, $tid, $nparams)
    if ($fm) { Write-Output ("FAULT MODULE: {0} +0x{1:X} (base 0x{2:X}, size {3} KB)" -f (Split-Path $fm.Name -Leaf), ($addr - $fm.Base), $fm.Base, [math]::Round($fm.Size / 1KB)) }
    else { Write-Output 'FAULT MODULE: address is not inside any loaded module' }
    # --- faulting thread stack (type 3) ---
    if ($streams.ContainsKey(3)) {
        $r3 = $streams[3].Rva; $nt = u32 $r3
        Write-Output ("threads: {0}" -f $nt)
        for ($i = 0; $i -lt $nt; $i++) {
            $e = $r3 + 4 + $i * 48
            $ttid = u32 $e
            if ($ttid -eq $tid) {
                $stackStart = u64 ($e + 24); $stackSize = u32 ($e + 32); $stackRva = u32 ($e + 36)
                Write-Output ("FAULTING THREAD stack: start=0x{0:X} size={1} bytes" -f $stackStart, $stackSize)
                $hits = @{}
                for ($o = 0; $o -le ($stackSize - 8); $o += 8) {
                    $v = [System.BitConverter]::ToUInt64($bytes, $stackRva + $o)
                    $m = Find-Module $v
                    if ($m -and $m.Name) { $leaf = Split-Path $m.Name -Leaf; $hits[$leaf] = ($hits[$leaf] + 1) }
                }
                Write-Output 'STACK POINTER HITS (rough call profile — return addresses landing in each module):'
                $hits.GetEnumerator() | Sort-Object Value -Descending | Select-Object -First 10 | ForEach-Object { Write-Output ("  {0,5}  {1}" -f $_.Value, $_.Key) }
                Write-Output 'TOP OF STACK (last 16 qwords, highest address first = most recent calls):'
                $nq = [math]::Min(16, [math]::Floor($stackSize / 8))
                for ($k = 0; $k -lt $nq; $k++) {
                    $o = $stackSize - 8 - ($k * 8)
                    $v = [System.BitConverter]::ToUInt64($bytes, $stackRva + $o)
                    $m = Find-Module $v
                    if ($m) { $where = (Split-Path $m.Name -Leaf) + (' +0x{0:X}' -f ($v - $m.Base)) } else { $where = '(no module)' }
                    Write-Output ("  0x{0:X}  {1}" -f $v, $where)
                }
            }
        }
    }
}
# --- Qt / Python module versions on record ---
Write-Output '--- LOADED MODULES (Qt + Python) ---'
$mods | Where-Object { $_.Name -match 'Qt6|python314|PyQt' } | ForEach-Object {
    Write-Output ("  {0}  base=0x{1:X} size={2} KB" -f (Split-Path $_.Name -Leaf), $_.Base, [math]::Round($_.Size / 1KB))
}
