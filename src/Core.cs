using System;
using System.IO;
using System.Linq;
using System.Text;
using System.Text.RegularExpressions;
using System.Collections.Generic;
using System.Diagnostics;
using System.ServiceProcess;
using System.Threading;
using System.Threading.Tasks;
using System.Net;
using System.Net.NetworkInformation;
using System.Web.Script.Serialization;
using Microsoft.Win32;

namespace ZapretManager {
public class Settings {
 public string Game="off", IPSet="none", DiscordFake="ACTIVE_DISCORD_UDP.bin", GameFake="ACTIVE_GAME_UDP.bin", StrategyId="current", StrategyName="Текущая рабочая";
 public bool AutoCheck=false, AutoStart=true;
 public string GameUdpPreset="native";
 public bool FaceitServerExclusions=true;
}
public class CommandResult { public int Exit; public string Output, Error; }
public class Snapshot { public string Directory, State, ImagePath; public int Start; }
public static class Core {
 [System.Runtime.InteropServices.DllImport("advapi32.dll",CharSet=System.Runtime.InteropServices.CharSet.Unicode,SetLastError=true)]static extern IntPtr OpenSCManager(string machine,string database,uint access);
 [System.Runtime.InteropServices.DllImport("advapi32.dll",CharSet=System.Runtime.InteropServices.CharSet.Unicode,SetLastError=true)]static extern IntPtr CreateService(IntPtr manager,string name,string display,uint access,uint type,uint start,uint error,string binary,string group,IntPtr tag,string dependencies,string account,string password);
 [System.Runtime.InteropServices.DllImport("advapi32.dll")]static extern bool CloseServiceHandle(IntPtr handle);
 [System.Runtime.InteropServices.DllImport("advapi32.dll",CharSet=System.Runtime.InteropServices.CharSet.Unicode,SetLastError=true)]static extern IntPtr OpenService(IntPtr manager,string name,uint access);
 [System.Runtime.InteropServices.DllImport("advapi32.dll",SetLastError=true)]static extern bool QueryServiceStatusEx(IntPtr service,int level,IntPtr buffer,int size,out int needed);
 [System.Runtime.InteropServices.DllImport("advapi32.dll",CharSet=System.Runtime.InteropServices.CharSet.Unicode,SetLastError=true)]static extern bool ChangeServiceConfig(IntPtr service,uint type,uint start,uint error,string binary,string group,IntPtr tag,string dependencies,string account,string password,string display);
 public static void ConfigureService(string name,string binary=null,uint start=0xffffffff,string[] dependencies=null){IntPtr manager=OpenSCManager(null,null,1);if(manager==IntPtr.Zero)throw new System.ComponentModel.Win32Exception();try{IntPtr service=OpenService(manager,name,2);if(service==IntPtr.Zero)throw new System.ComponentModel.Win32Exception();try{string deps=dependencies==null?null:string.Join("\0",dependencies)+"\0\0";if(!ChangeServiceConfig(service,0xffffffff,start,0xffffffff,binary,null,IntPtr.Zero,deps,null,null,null))throw new System.ComponentModel.Win32Exception();}finally{CloseServiceHandle(service);}}finally{CloseServiceHandle(manager);}}
 public static void Preflight(){foreach(string file in new[]{"winws2.exe","cygwin1.dll","WinDivert.dll","WinDivert64.sys","app\\Zapret2Service.exe"})if(!File.Exists(PathOf(file)))throw new FileNotFoundException("Отсутствует "+file+". Повторите установку полного установщика (не отдельного EXE приложения). Файл мог быть удалён или заблокирован.",PathOf(file));string manifest=PathOf("runtime-sha256.json");if(File.Exists(manifest)){var hashes=Read<Dictionary<string,string>>(manifest);foreach(var h in hashes){if(!File.Exists(PathOf(h.Key)))throw new FileNotFoundException("Отсутствует компонент "+h.Key+". Запустите установщик для восстановления.");using(var sha=System.Security.Cryptography.SHA256.Create())using(var stream=File.OpenRead(PathOf(h.Key))){string actual=BitConverter.ToString(sha.ComputeHash(stream)).Replace("-","");if(!string.Equals(actual,h.Value,StringComparison.OrdinalIgnoreCase))throw new InvalidOperationException("Компонент "+h.Key+" повреждён или имеет несовместимую версию. Запустите новый установщик для восстановления.");}}}}
 public static void StopOrphanEngine(){foreach(var p in Process.GetProcessesByName("winws2")){using(p){string exe;try{exe=p.MainModule.FileName;}catch{continue;}if(!string.Equals(Path.GetFullPath(exe),PathOf("winws2.exe"),StringComparison.OrdinalIgnoreCase))continue;p.Kill();if(!p.WaitForExit(8000))throw new System.TimeoutException("Старая копия winws2 ещё завершает работу");}}}
 static int ServicePID(){return GetServicePID(Service);} public static int GetServicePID(string name){IntPtr manager=OpenSCManager(null,null,1);if(manager==IntPtr.Zero)return 0;try{IntPtr service=OpenService(manager,name,4);if(service==IntPtr.Zero)return 0;try{IntPtr b=System.Runtime.InteropServices.Marshal.AllocHGlobal(36);try{int needed;return QueryServiceStatusEx(service,0,b,36,out needed)?System.Runtime.InteropServices.Marshal.ReadInt32(b,28):0;}finally{System.Runtime.InteropServices.Marshal.FreeHGlobal(b);}}finally{CloseServiceHandle(service);}}finally{CloseServiceHandle(manager);}}
 [System.Runtime.InteropServices.DllImport("iphlpapi.dll",SetLastError=true)]static extern uint GetIpForwardTable(IntPtr table,ref int size,bool order);
 public static HashSet<int> InternetInterfaces(){var result=new HashSet<int>();int size=0;GetIpForwardTable(IntPtr.Zero,ref size,false);if(size<4)return result;IntPtr buffer=System.Runtime.InteropServices.Marshal.AllocHGlobal(size);try{if(GetIpForwardTable(buffer,ref size,false)!=0)return result;int count=System.Runtime.InteropServices.Marshal.ReadInt32(buffer);int best=int.MaxValue,bestIndex=-1;var halves=new Dictionary<int,int>();for(int n=0;n<count;n++){int offset=4+n*56;uint dest=unchecked((uint)System.Runtime.InteropServices.Marshal.ReadInt32(buffer,offset));uint mask=unchecked((uint)System.Runtime.InteropServices.Marshal.ReadInt32(buffer,offset+4));int idx=System.Runtime.InteropServices.Marshal.ReadInt32(buffer,offset+16);int metric=System.Runtime.InteropServices.Marshal.ReadInt32(buffer,offset+36);if(mask==0&&dest==0&&metric<best){best=metric;bestIndex=idx;}if(mask==128&&(dest==0||dest==128)){int bit=dest==0?1:2;halves[idx]=(halves.ContainsKey(idx)?halves[idx]:0)|bit;}}foreach(var h in halves)if(h.Value==3)result.Add(h.Key);if(result.Count==0&&bestIndex>=0)result.Add(bestIndex);return result;}finally{System.Runtime.InteropServices.Marshal.FreeHGlobal(buffer);}}
 public static string Root=FindRoot(); public static string FindRoot(){string candidate=Path.GetFullPath(Path.Combine(AppDomain.CurrentDomain.BaseDirectory,".."));return (File.Exists(Path.Combine(candidate,"winws2.exe"))||File.Exists(Path.Combine(candidate,"manager-base.template")))?candidate:Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.CommonApplicationData),"zapret2");}
 public static readonly SemaphoreSlim OperationGate=new SemaphoreSlim(1,1);
 public static string Service="zapret2";
 public static void CreateAuxService(string name,string binary){IntPtr manager=OpenSCManager(null,null,3);if(manager==IntPtr.Zero)throw new System.ComponentModel.Win32Exception();try{IntPtr s=CreateService(manager,name,"Zapret 2 — исключения приложений",0xF01FF,0x10,3,1,binary,null,IntPtr.Zero,null,null,null);if(s==IntPtr.Zero)throw new System.ComponentModel.Win32Exception();CloseServiceHandle(s);}finally{CloseServiceHandle(manager);}}
 public static JavaScriptSerializer Json=new JavaScriptSerializer { MaxJsonLength=10000000 };
 public static string PathOf(string p) { return Path.Combine(Root,p); }
 public static string ReadShared(string path){for(int n=0;;n++){try{using(var file=new FileStream(path,FileMode.Open,FileAccess.Read,FileShare.ReadWrite|FileShare.Delete))using(var reader=new StreamReader(file,Encoding.UTF8,true))return reader.ReadToEnd();}catch(IOException){if(n>=5)throw;Thread.Sleep(20*(n+1));}}}
 public static T Read<T>(string path) { return new JavaScriptSerializer { MaxJsonLength=10000000 }.Deserialize<T>(ReadShared(path)); }
 public static void Write(string path,object value) { string tmp=path+"."+Guid.NewGuid().ToString("N")+".tmp";try{File.WriteAllText(tmp,new JavaScriptSerializer {MaxJsonLength=10000000}.Serialize(value),new UTF8Encoding(false));for(int n=0;;n++){try{if(File.Exists(path))File.Replace(tmp,path,null);else File.Move(tmp,path);return;}catch(IOException){if(n>=5)throw;Thread.Sleep(20*(n+1));}}}finally{if(File.Exists(tmp))try{File.Delete(tmp);}catch{}} }
 public static Settings Load() { return File.Exists(PathOf("manager-settings.json"))?Read<Settings>(PathOf("manager-settings.json")):new Settings(); }
 public static void Guard() { if(File.Exists(PathOf("autotune-pending.json"))) throw new InvalidOperationException("Не завершён автоподбор. Сначала восстановите предыдущую стратегию."); }
 public static string State() { using(var s=new ServiceController(Service)) { try{return s.Status.ToString();}catch{return "NotInstalled";} } }
 public static async Task<CommandResult> Run(string exe,string args,CancellationToken token,int timeout=15000,string extraPath=null,string workingDirectory=null) {
  var pi=new ProcessStartInfo(exe,args) { UseShellExecute=false,CreateNoWindow=true,RedirectStandardOutput=true,RedirectStandardError=true };
  if(workingDirectory!=null)pi.WorkingDirectory=workingDirectory;
  if(extraPath!=null)pi.EnvironmentVariables["PATH"]=extraPath+";"+Environment.GetEnvironmentVariable("PATH");
  using(var p=new Process {StartInfo=pi}) { p.Start(); var stdout=p.StandardOutput.ReadToEndAsync(); var stderr=p.StandardError.ReadToEndAsync(); var watch=Stopwatch.StartNew();
   try { while(!p.HasExited) { token.ThrowIfCancellationRequested(); if(watch.ElapsedMilliseconds>timeout)throw new System.TimeoutException(exe+": истекло время ожидания"); await Task.Delay(50,token); }
    return new CommandResult {Exit=p.ExitCode,Output=await stdout,Error=await stderr};
   } finally { if(!p.HasExited) { try{p.Kill();p.WaitForExit(3000);}catch{} } }
  }
 }
 public static string Quote(string s) { if(s.Contains("\"") || s.Contains("\n") || s.Contains("\r"))throw new ArgumentException("Недопустимое значение");return "\""+s+"\""; }
 public static string Build(Settings s,string baseText=null) {
  if(!new[]{"off","tcp","udp","all"}.Contains(s.Game) || !new[]{"none","loaded","any"}.Contains(s.IPSet))throw new ArgumentException("Неизвестный фильтр");
  if(!new[]{"native","alt12-exp"}.Contains(s.GameUdpPreset??"native"))throw new ArgumentException("Неизвестный игровой UDP-профиль");
  foreach(string fake in new[]{s.DiscordFake,s.GameFake}) if(Path.GetFileName(fake)!=fake || !File.Exists(PathOf("files\\"+fake)))throw new ArgumentException("Файл фейка отсутствует: "+fake);
  string text=baseText??File.ReadAllText(PathOf("manager-base.txt"));
  text=text.Replace("files\\ACTIVE_DISCORD_UDP.bin","files\\"+s.DiscordFake);
  foreach(string blob in new[]{"quic_google","discord_udp"})text=text.Replace("--lua-desync=fake:blob="+blob+":repeats=4","--lua-desync=fake:blob="+blob+":repeats=4:payload=all");
  string ex="--hostlist-exclude="+Quote(PathOf("lists\\list-exclude.txt"))+" --hostlist-exclude="+Quote(PathOf("lists\\list-exclude-user.txt"))+" --ipset-exclude="+Quote(PathOf("lists\\ipset-exclude.txt"))+" --ipset-exclude="+Quote(PathOf("lists\\ipset-exclude-user.txt"));
  string gameEx="--ipset-exclude="+Quote(PathOf("lists\\ipset-exclude.txt"))+" --ipset-exclude="+Quote(PathOf("lists\\ipset-exclude-user.txt"));
  string scope=s.IPSet=="loaded"?"--ipset="+Quote(PathOf("lists\\ipset-all.txt")):"";
  if(s.IPSet!="none") {
   text+="\r\n--new\r\n--filter-tcp=80,443,8443 "+scope+" "+ex+" --out-range=-d10 --payload=tls_client_hello,http_req\r\n--lua-desync=fake:blob=tls_max:tcp_ts=-600000:tcp_ts_up:repeats=4\r\n--lua-desync=multisplit:pos=1:seqovl=480:seqovl_pattern=stun2:tcp_ts_up\r\n--new\r\n--filter-udp=443 "+scope+" "+ex+" --payload=quic_initial --lua-desync=fake:blob=quic_google:repeats=11\r\n";
   if(s.Game=="tcp"||s.Game=="all") {text=text.Replace("--wf-tcp-out=80,443,2053,2083,2087,2096,8443","--wf-tcp-out=80,443,1024-65535");text+="\r\n--new\r\n--filter-tcp=1024-65535 "+scope+" "+ex+" --out-range=-n4 --payload=all\r\n--lua-desync=fake:blob=tls_max:tcp_ts=-600000:tcp_ts_up:repeats=8\r\n--lua-desync=multisplit:pos=1:seqovl=664:seqovl_pattern=tls_max:tcp_ts_up\r\n";}
   if(s.Game=="udp"||s.Game=="all") {text=text.Replace("--wf-udp-out=19294-19344,50000-50100","--wf-udp-out=443,1024-65535");text="--blob=game_udp:@"+Quote(PathOf("files\\"+s.GameFake))+"\r\n"+text;text+="\r\n--new\r\n--filter-udp=1024-65535 "+scope+" "+gameEx+" --out-range=-n4 --payload=all\r\n--lua-desync=fake:blob=quic_google:repeats=5\r\n--lua-desync=fake:blob=game_udp:repeats=5\r\n";}
  }
  foreach(string part in new[]{"blob=tls_max:tcp_ts=-600000:tcp_ts_up:repeats=8","pos=1:seqovl=664:seqovl_pattern=tls_max:tcp_ts_up","blob=quic_google:repeats=5","blob=game_udp:repeats=5"})text=text.Replace(part,part+":payload=all");
  if(s.GameUdpPreset=="alt12-exp"&&(s.Game=="udp"||s.Game=="all")&&s.IPSet!="none"){
   string blob=PathOf("files\\faceit_legacy_udp.bin");if(!File.Exists(blob))throw new FileNotFoundException("Фейк совместимости ALT12 / EXP отсутствует",blob);
   text="--blob=faceit_legacy_udp:@"+Quote(blob)+"\r\n"+text;
   text=Regex.Replace(text,@"(?m)(--filter-udp=1024-65535[^\r\n]*)(\r?\n)--lua-desync=fake:blob=quic_google:repeats=5:payload=all\r?\n--lua-desync=fake:blob=game_udp:repeats=5:payload=all",m=>m.Groups[1].Value.Replace("--out-range=-n4","--out-range=<n4").Replace("--payload=all","--filter-l7=unknown --payload=unknown")+m.Groups[2].Value+"--lua-desync=fake:blob=faceit_legacy_udp:repeats=10:payload=unknown");
  }
  string face=PathOf("files\\faceit-game-exclude.txt");if(s.FaceitServerExclusions&&File.Exists(face)&&File.ReadAllLines(face).Any(l=>Regex.IsMatch(l,@"^\d+\.")))text=Regex.Replace(text,@"(?m)(--filter-udp=[^\r\n]*)",m=>m.Value+" --ipset-exclude="+Quote(face));
  return text;
 }
 public static async Task Validate(string text,CancellationToken token) {
  string f=PathOf("native-check-"+Guid.NewGuid().ToString("N")+".txt");File.WriteAllText(f,"--dry-run\r\n--wf-dup-check=0\r\n"+text,Encoding.ASCII);
  try {var r=await Run(PathOf("winws2.exe"),"@"+Path.GetFileName(f),token,workingDirectory:Root);if(r.Exit==unchecked((int)0xC0000142)){await Task.Delay(500,token);r=await Run(PathOf("winws2.exe"),"@"+Path.GetFileName(f),token,workingDirectory:Root);}if(r.Exit!=0){File.Copy(f,PathOf("native-last-rejected.txt"),true);throw new InvalidOperationException((r.Exit==unchecked((int)0xC0000142)?"Движок winws2 не запустился: ошибка инициализации DLL. Используйте «Проверить и исправить».":"winws2 отклонил конфигурацию (exit="+r.Exit+"):")+"\\n"+r.Output+r.Error);}}finally{File.Delete(f);}
 }
 public static void Image(string text) {ConfigureService(Service,Quote(ServicePaths.Host)+" --engine-service "+Service);}
 public static void Startup(bool auto) {ConfigureService(Service,start:auto?2u:3u);}
 public static void Control(string mode) {
  if(mode=="Restart"){Control("Off");Control("On");return;}
  using(var s=new ServiceController(Service)) {
   if(mode=="On") {
    Preflight();if(State()=="NotInstalled")throw new InvalidOperationException("Служба не установлена. Нажмите «Установить».");string image;using(var key=Registry.LocalMachine.OpenSubKey(@"SYSTEM\CurrentControlSet\Services\"+Service))image=(string)key.GetValue("ImagePath","");string expected=Quote(ServicePaths.Host)+" --engine-service "+Service;if(!string.Equals(image,expected,StringComparison.OrdinalIgnoreCase)){if(!ServicePaths.Known(image,true))throw new InvalidOperationException("Имя службы занято неизвестной программой: "+image);if(s.Status!=ServiceControllerStatus.Stopped){Control("Off");s.Refresh();}ConfigureService(Service,expected);}
    if(Service=="zapret2"||Exclusions.Testing)Exclusions.Ensure().GetAwaiter().GetResult();
    if(Service=="zapret2") {using(var old=new ServiceController("zapret")){try{if(old.Status!=ServiceControllerStatus.Stopped){old.Stop();old.WaitForStatus(ServiceControllerStatus.Stopped,TimeSpan.FromSeconds(15));}using(var k=Registry.LocalMachine.OpenSubKey(@"SYSTEM\CurrentControlSet\Services\zapret",true)){if(k!=null)k.SetValue("Start",4);}}catch(InvalidOperationException){}}}
    using(var k=Registry.LocalMachine.OpenSubKey(@"SYSTEM\CurrentControlSet\Services\"+Service)){if(Convert.ToInt32(k.GetValue("Start"))==4)ConfigureService(Service,start:3);}
    try{if(s.Status!=ServiceControllerStatus.Running){StopOrphanEngine();s.Start();}s.WaitForStatus(ServiceControllerStatus.Running,TimeSpan.FromSeconds(55));}catch(Exception e){string health=PathOf(Service+"-engine-status.json");if(File.Exists(health)){var h=Read<EngineHealth>(health);if(h.Error!="")throw new Exception(h.Error,e);}throw new Exception("Не удалось запустить службу: "+e.Message+". См. engine-service.log и диагностику.",e);}Thread.Sleep(300);s.Refresh();if(s.Status!=ServiceControllerStatus.Running)throw new Exception("Служба завершилась после запуска. См. engine-service.log");
   } else {int pid=ServicePID();if(s.Status!=ServiceControllerStatus.Stopped)s.Stop();s.WaitForStatus(ServiceControllerStatus.Stopped,TimeSpan.FromSeconds(15));if(pid>0){try{using(var old=Process.GetProcessById(pid)){if(!old.WaitForExit(10000))throw new System.TimeoutException("Процесс службы ещё завершает работу. Повторите запуск позже.");}}catch(ArgumentException){}}}
  }
  if(mode!="On"&&(Service=="zapret2"||Exclusions.Testing))Exclusions.Stop();
 }
 public static Snapshot Backup() {
  string dir=PathOf("native-backups\\"+DateTime.Now.ToString("yyyyMMdd-HHmmss")+"-"+Guid.NewGuid().ToString("N").Substring(0,8));Directory.CreateDirectory(dir);
  foreach(string f in new[]{"manager-base.txt","config.txt","manager-settings.json"})File.Copy(PathOf(f),Path.Combine(dir,f));
  if(File.Exists(PathOf("app-exclusions.json")))File.Copy(PathOf("app-exclusions.json"),Path.Combine(dir,"app-exclusions.json"));
  var snap=new Snapshot {Directory=dir,State=State(),Start=3,ImagePath=""};using(var k=Registry.LocalMachine.OpenSubKey(@"SYSTEM\CurrentControlSet\Services\"+Service)){if(k!=null){snap.Start=Convert.ToInt32(k.GetValue("Start"));snap.ImagePath=(string)k.GetValue("ImagePath");}}
  Write(Path.Combine(dir,"native-manifest.json"),snap);return snap;
 }
 public static void Restore(Snapshot snap) {
  string full=Path.GetFullPath(snap.Directory);if(!full.StartsWith(Path.GetFullPath(PathOf("native-backups"))+Path.DirectorySeparatorChar,StringComparison.OrdinalIgnoreCase))throw new Exception("Недопустимая резервная копия");
  if(State()!="NotInstalled")Control("Off");foreach(string f in new[]{"manager-base.txt","config.txt","manager-settings.json"})File.Copy(Path.Combine(full,f),PathOf(f),true);
  using(var k=Registry.LocalMachine.OpenSubKey(@"SYSTEM\CurrentControlSet\Services\"+Service,true)){if(k!=null){ConfigureService(Service,snap.ImagePath,start:3);}}
  if(File.Exists(Path.Combine(full,"app-exclusions.json")))File.Copy(Path.Combine(full,"app-exclusions.json"),PathOf("app-exclusions.json"),true);
  if(snap.State=="Running")Control("On");using(var k=Registry.LocalMachine.OpenSubKey(@"SYSTEM\CurrentControlSet\Services\"+Service,true)){if(k!=null)ConfigureService(Service,start:(uint)snap.Start);}
 }
 public static async Task Apply(Settings settings,CancellationToken token,string baseText=null,bool tuning=false) {
  if(!tuning)Guard();string text=Build(settings,baseText);await Validate(text,token);token.ThrowIfCancellationRequested();var backup=Backup();
  try {if(backup.State=="Running")Control("Off");if(baseText!=null)File.WriteAllText(PathOf("manager-base.txt"),baseText,Encoding.ASCII);File.WriteAllText(PathOf("config.txt"),text+"\r\n",Encoding.ASCII);if(backup.State!="NotInstalled"){Image(text);Startup(settings.AutoStart);}Write(PathOf("manager-settings.json"),settings);if(backup.State=="Running")Control("On");}
  catch{Restore(backup);throw;}
 }
 public static async Task Install(CancellationToken token) {
  Guard();var s=Load();var text=Build(s);await Validate(text,token);
  if(State()=="NotInstalled"){IntPtr manager=OpenSCManager(null,null,3);if(manager==IntPtr.Zero)throw new System.ComponentModel.Win32Exception();try{IntPtr handle=CreateService(manager,Service,"zapret 2 DPI bypass",0xF01FF,0x10,s.AutoStart?2u:3u,1,Quote(ServicePaths.Host)+" --engine-service "+Service,null,IntPtr.Zero,null,null,null);if(handle==IntPtr.Zero)throw new System.ComponentModel.Win32Exception();CloseServiceHandle(handle);File.WriteAllText(PathOf("config.txt"),text+"\r\n",Encoding.ASCII);}finally{CloseServiceHandle(manager);}}else await Apply(s,token);
  Control("On");
 }
 public static async Task Remove(CancellationToken token) {Guard();if(State()!="NotInstalled"){Control("Off");var r=await Run(Path.Combine(Environment.SystemDirectory,"sc.exe"),"delete "+Service,token);if(r.Exit!=0)throw new Exception(r.Output+r.Error);}if(Service=="zapret2")await Exclusions.Remove();}
 public static string Proxy() {using(var k=Registry.CurrentUser.OpenSubKey(@"Software\Microsoft\Windows\CurrentVersion\Internet Settings")){if(k==null||Convert.ToInt32(k.GetValue("ProxyEnable",0))!=1)return "";string p=(string)k.GetValue("ProxyServer","");Match m=Regex.Match(p,@"^(?:127\.0\.0\.1|localhost):(\d+)$");if(m.Success&&!IPGlobalProperties.GetIPGlobalProperties().GetActiveTcpListeners().Any(x=>x.Port==int.Parse(m.Groups[1].Value)))return "";return p;}}
 public static string Context() {
  var parts=new List<string>();string proxy=Proxy();if(proxy!="")parts.Add("Proxy включён: "+proxy);
  var active=InternetInterfaces();foreach(var n in NetworkInterface.GetAllNetworkInterfaces().Where(n=>n.OperationalStatus==OperationalStatus.Up)) {
   bool virtualVpn=n.NetworkInterfaceType==NetworkInterfaceType.Tunnel||n.NetworkInterfaceType==NetworkInterfaceType.Ppp||Regex.IsMatch(n.Name+" "+n.Description,"wireguard|wintun|openvpn|vpn|tun|tap",RegexOptions.IgnoreCase);
   if(virtualVpn&&n.Supports(NetworkInterfaceComponent.IPv4)){try{var ipv4=n.GetIPProperties().GetIPv4Properties();if(ipv4!=null&&active.Contains(ipv4.Index))parts.Add("VPN включён: "+n.Name);}catch(NetworkInformationException){}}
  }
  return string.Join(" | ",parts);
 }
 public static Task<string> Fetch(string url){return Downloads.Fetch(url,CancellationToken.None);}
 public static int ValidateIPSet(string text) {int count=0;foreach(string raw in Regex.Split(text,@"\r?\n")){string l=raw.Trim();if(l==""||l.StartsWith("#"))continue;var p=l.Split('/');IPAddress ip;int prefix;if(p.Length>2||!IPAddress.TryParse(p[0],out ip)|| (p.Length==2&&(!int.TryParse(p[1],out prefix)||prefix<0||prefix>(ip.AddressFamily==System.Net.Sockets.AddressFamily.InterNetwork?32:128))))throw new Exception("Некорректный IP: "+l);count++;}if(count==0)throw new Exception("Пустой IPSet");return count;}
 public static async Task<string> UpdateIPs(CancellationToken token){Guard();var text=await Downloads.IPSet(token);token.ThrowIfCancellationRequested();int count=ValidateIPSet(text);string f=PathOf("lists\\ipset-all.txt");byte[] old=File.Exists(f)?File.ReadAllBytes(f):null;if(old!=null)File.WriteAllBytes(f+".native-backup",old);try{File.WriteAllText(f,text,Encoding.ASCII);await Apply(Load(),token);}catch{if(old==null)File.Delete(f);else File.WriteAllBytes(f,old);throw;}return "IPSet обновлён: "+count;}
 public static string MergeHosts(string original,string update){var domains=new HashSet<string>(StringComparer.OrdinalIgnoreCase);var lines=new List<string>();foreach(var raw in Regex.Split(update,@"\r?\n")){string l=raw.Split('#')[0].Trim();if(l=="")continue;string[] p=Regex.Split(l,@"\s+");IPAddress ip;if(p.Length<2||!IPAddress.TryParse(p[0],out ip)||p.Skip(1).Any(d=>!Regex.IsMatch(d,@"^[a-zA-Z0-9][a-zA-Z0-9.-]+$")))throw new Exception("Некорректный hosts");foreach(string d in p.Skip(1))domains.Add(d);lines.Add(l);}if(lines.Count==0)throw new Exception("Пустой hosts");var kept=new List<string>();foreach(string l in Regex.Split(Regex.Replace(original,@"(?ms)^# BEGIN ZAPRET2 MANAGER\r?\n.*?^# END ZAPRET2 MANAGER\r?\n?",""),@"\r?\n")){var p=Regex.Split(l.Split('#')[0].Trim(),@"\s+");if(p.Length<2){kept.Add(l);continue;}var left=p.Skip(1).Where(d=>!domains.Contains(d)).ToArray();if(left.Length==p.Length-1)kept.Add(l);else if(left.Length>0)kept.Add(p[0]+" "+string.Join(" ",left));}return string.Join("\r\n",kept).TrimEnd()+"\r\n\r\n# BEGIN ZAPRET2 MANAGER\r\n"+string.Join("\r\n",lines)+"\r\n# END ZAPRET2 MANAGER\r\n";}
 public static async Task<string> Updates(){string json=await Fetch("https://api.github.com/repos/bol-van/zapret-win-bundle/contents/zapret-winws/winws2.exe");var m=ReadDictionary(json);byte[] b=File.ReadAllBytes(PathOf("winws2.exe"));byte[] header=Encoding.ASCII.GetBytes("blob "+b.Length+"\0");using(var sha=System.Security.Cryptography.SHA1.Create()){string hash=BitConverter.ToString(sha.ComputeHash(header.Concat(b).ToArray())).Replace("-","").ToLowerInvariant();return hash==(string)m["sha"]?"Установлен текущий официальный winws2.":"Доступен новый winws2: https://github.com/bol-van/zapret-win-bundle";}}
 static Dictionary<string,object> ReadDictionary(string s){return new JavaScriptSerializer().Deserialize<Dictionary<string,object>>(s);}
}
}

