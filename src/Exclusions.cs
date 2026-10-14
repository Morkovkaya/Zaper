using System;
using System.IO;
using System.Linq;
using System.Collections.Generic;
using System.Diagnostics;
using System.Net;
using System.Runtime.InteropServices;
using System.ServiceProcess;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Win32;

namespace ZapretManager {
public class ExclusionConfig { public string RequestId; public bool Enabled=true; public string[] Applications=new string[0]; }
public static class Exclusions {
 public static string ServiceName="zapret2-exclusions";internal static bool Testing;
 public static ExclusionConfig Load(){return File.Exists(Core.PathOf("app-exclusions.json"))?Core.Read<ExclusionConfig>(Core.PathOf("app-exclusions.json")):new ExclusionConfig();}
 public static string Normalize(string path){if(string.IsNullOrWhiteSpace(path)||!Path.IsPathRooted(path)||!path.EndsWith(".exe",StringComparison.OrdinalIgnoreCase))throw new ArgumentException("Выберите полный путь к EXE приложения");return Path.GetFullPath(path);}
 public static bool Matches(ExclusionConfig c,string path){return c.Enabled&&path!=null&&(c.Applications??new string[0]).Any(p=>string.Equals(Normalize(p),path,StringComparison.OrdinalIgnoreCase));}
 public static string State(){try{using(var s=new ServiceController(ServiceName))return s.Status.ToString();}catch{return "NotInstalled";}}
 static async Task SC(string args){var r=await Core.Run(Path.Combine(Environment.SystemDirectory,"sc.exe"),args,CancellationToken.None);if(r.Exit!=0)throw new Exception(r.Output+r.Error);}
 public static async Task Ensure(){
  if(Core.Service!="zapret2"&&!Testing)return;
  string expected=Core.Quote(ServicePaths.Host)+" --exclusion-service "+ServiceName;bool resume=false;
  if(State()=="NotInstalled")Core.CreateAuxService(ServiceName,expected);
  string image;using(var key=Registry.LocalMachine.OpenSubKey(@"SYSTEM\CurrentControlSet\Services\"+ServiceName))image=(string)key.GetValue("ImagePath","");
  if(!string.Equals(image,expected,StringComparison.OrdinalIgnoreCase)){
   if(!ServicePaths.Known(image,false))throw new InvalidOperationException("Имя службы исключений занято неизвестной программой: "+image);
   resume=Core.State()=="Running";if(resume)Core.Control("Off");using(var service=new ServiceController(ServiceName)){if(service.Status!=ServiceControllerStatus.Stopped){service.Stop();service.WaitForStatus(ServiceControllerStatus.Stopped,TimeSpan.FromSeconds(20));}}
   Core.ConfigureService(ServiceName,expected,start:3);
  }
  using(var key=Registry.LocalMachine.OpenSubKey(@"SYSTEM\CurrentControlSet\Services\"+Core.Service)){if(key!=null){var deps=(string[])key.GetValue("DependOnService",new string[0]);if(!deps.Contains(ServiceName))Core.ConfigureService(Core.Service,dependencies:deps.Concat(new[]{ServiceName}).ToArray());}}
  using(var key=Registry.LocalMachine.OpenSubKey(@"SYSTEM\CurrentControlSet\Services\"+ServiceName)){if(Convert.ToInt32(key.GetValue("Start"))==4)Core.ConfigureService(ServiceName,start:3);}
  using(var service=new ServiceController(ServiceName)){if(service.Status!=ServiceControllerStatus.Running)service.Start();service.WaitForStatus(ServiceControllerStatus.Running,TimeSpan.FromSeconds(25));}
  if(resume)Core.Control("On");await Task.FromResult(0);
 }
 public static void Stop(){if((Core.Service!="zapret2"&&!Testing)||State()=="NotInstalled")return;using(var key=Registry.LocalMachine.OpenSubKey(@"SYSTEM\CurrentControlSet\Services\"+ServiceName)){if(key==null||!(ServicePaths.Known((string)key.GetValue("ImagePath",""),false)&&ServicePaths.AtRoot((string)key.GetValue("ImagePath",""))))return;}int pid=Core.GetServicePID(ServiceName);using(var s=new ServiceController(ServiceName)){if(s.Status!=ServiceControllerStatus.Stopped)s.Stop();s.WaitForStatus(ServiceControllerStatus.Stopped,TimeSpan.FromSeconds(15));}if(pid>0){try{using(var process=Process.GetProcessById(pid)){if(!process.WaitForExit(8000))throw new System.TimeoutException("Процесс службы исключений ещё завершает работу");}}catch(ArgumentException){}}}
 public static async Task Remove(){if(State()=="NotInstalled")return;using(var k=Registry.LocalMachine.OpenSubKey(@"SYSTEM\CurrentControlSet\Services\"+ServiceName)){string image=(string)k.GetValue("ImagePath","");if(!ServicePaths.Known(image,false)||!ServicePaths.AtRoot(image))return;}Stop();await SC("delete "+ServiceName);}
 public static string Identity(ExclusionConfig c){if(!string.IsNullOrEmpty(c.RequestId))return c.RequestId;using(var sha=System.Security.Cryptography.SHA256.Create())return "legacy-"+BitConverter.ToString(sha.ComputeHash(System.Text.Encoding.UTF8.GetBytes(Core.Json.Serialize(c)))).Replace("-","");}
 public static async Task Save(ExclusionConfig config){
  Core.Guard();config.Applications=(config.Applications??new string[0]).Select(Normalize).Distinct(StringComparer.OrdinalIgnoreCase).ToArray();foreach(string p in config.Applications)if(!File.Exists(p))throw new FileNotFoundException("EXE не найден",p);
  config.RequestId=Guid.NewGuid().ToString("N");string file=Core.PathOf("app-exclusions.json");byte[] old=File.Exists(file)?File.ReadAllBytes(file):null;
  try{Core.Write(file,config);if(Core.State()!="Running")return;await Ensure();string detail="";for(int n=0;n<150;n++){await Task.Delay(100);string statusFile=Core.PathOf("app-exclusions-status.json");if(!File.Exists(statusFile))continue;try{var status=Core.Read<ExclusionHealth>(statusFile);if(status.RequestId!=config.RequestId)continue;detail=status.Error;if(status.Ready&&status.PID==Core.GetServicePID(ServiceName))return;}catch(IOException){continue;}}
   throw new System.TimeoutException("Служба не подтвердила запрос за 15 секунд (состояние: "+State()+"). "+detail+" См. exclusions-service.log.");
  }catch{if(old==null){if(File.Exists(file))File.Delete(file);}else{var prior=new System.Web.Script.Serialization.JavaScriptSerializer().Deserialize<ExclusionConfig>(System.Text.Encoding.UTF8.GetString(old).TrimStart('\uFEFF'));prior.RequestId=Guid.NewGuid().ToString("N");Core.Write(file,prior);}throw;}
 }
 public static string[] Steam(){var result=new List<string>();string dir=null;using(var k=Registry.CurrentUser.OpenSubKey(@"Software\Valve\Steam"))if(k!=null)dir=k.GetValue("SteamPath") as string;if(dir==null)dir=Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.ProgramFilesX86),"Steam");if(Directory.Exists(dir)){string exe=Path.Combine(dir,"steam.exe");if(File.Exists(exe))result.Add(exe);string bin=Path.Combine(dir,"bin");if(Directory.Exists(bin))result.AddRange(Directory.GetFiles(bin,"steamwebhelper.exe",SearchOption.AllDirectories));}return result.Select(Path.GetFullPath).Distinct(StringComparer.OrdinalIgnoreCase).ToArray();}
}
public class ExclusionHealth {public long Revision,Bypassed,Processed;public int PID;public string RequestId,Warning="";public bool Ready;public string Error="";public string Updated;}
public class ExclusionService:ServiceBase {
 CancellationTokenSource stop;Task work;
 public ExclusionService(){ServiceName=Exclusions.ServiceName;CanStop=true;}
 protected override void OnStart(string[] args){stop=new CancellationTokenSource();using(var ready=new ManualResetEventSlim()){int signalled=0;work=Task.Run(()=>{while(!stop.IsCancellationRequested){try{ExclusionWorker.Run(stop.Token,()=>{if(Interlocked.Exchange(ref signalled,1)==0)ready.Set();});}catch(Exception e){ExclusionWorker.Log("worker recovery: "+e.Message);if(Thread.VolatileRead(ref signalled)==0)throw;}if(!stop.IsCancellationRequested)stop.Token.WaitHandle.WaitOne(1000);}});for(int n=0;n<100&&!ready.IsSet;n++){if(work.IsCompleted)work.GetAwaiter().GetResult();Thread.Sleep(100);}if(!ready.IsSet){stop.Cancel();throw new System.TimeoutException("Служба исключений не готова");}}}
 protected override void OnStop(){stop.Cancel();try{if(!work.Wait(10000))throw new System.TimeoutException("Исключения ещё завершаются");}catch(AggregateException){}stop.Dispose();}
}
public static class ExclusionWorker {
 internal static bool TestMode;static int testFault;
 [DllImport("kernel32.dll",CharSet=CharSet.Unicode)]static extern bool SetDllDirectory(string path);
 [DllImport("WinDivert.dll",CallingConvention=CallingConvention.Cdecl,SetLastError=true)]internal static extern IntPtr WinDivertOpen([MarshalAs(UnmanagedType.LPStr)]string filter,int layer,short priority,ulong flags);
 [DllImport("WinDivert.dll",CallingConvention=CallingConvention.Cdecl,SetLastError=true)]internal static extern bool WinDivertRecv(IntPtr handle,byte[] packet,uint size,out uint length,byte[] address);
 [DllImport("WinDivert.dll",CallingConvention=CallingConvention.Cdecl,SetLastError=true)]internal static extern bool WinDivertSend(IntPtr handle,byte[] packet,uint size,out uint sent,byte[] address);
 [DllImport("WinDivert.dll",CallingConvention=CallingConvention.Cdecl)]internal static extern bool WinDivertShutdown(IntPtr handle,int how);
 [DllImport("WinDivert.dll",CallingConvention=CallingConvention.Cdecl)]internal static extern bool WinDivertClose(IntPtr handle);
 [DllImport("iphlpapi.dll")]static extern uint GetExtendedTcpTable(IntPtr table,ref int size,bool order,int family,int type,uint reserved);
 [DllImport("iphlpapi.dll")]static extern uint GetExtendedUdpTable(IntPtr table,ref int size,bool order,int family,int type,uint reserved);
 [DllImport("kernel32.dll",SetLastError=true)]static extern IntPtr OpenProcess(uint access,bool inherit,int pid);
 [DllImport("kernel32.dll",CharSet=CharSet.Unicode,SetLastError=true)]static extern bool QueryFullProcessImageName(IntPtr handle,uint flags,System.Text.StringBuilder name,ref int size);
 [DllImport("kernel32.dll")]static extern bool CloseHandle(IntPtr handle);
 [DllImport("kernel32.dll")]static extern uint WaitForSingleObject(IntPtr handle,uint milliseconds);
 sealed class ProcessEntry {public IntPtr Handle;public string Path;}
 sealed class ProcessPaths:IDisposable {readonly Dictionary<int,ProcessEntry> entries=new Dictionary<int,ProcessEntry>();public string Get(int pid){ProcessEntry e;if(entries.TryGetValue(pid,out e)){if(WaitForSingleObject(e.Handle,0)==258)return e.Path;CloseHandle(e.Handle);entries.Remove(pid);}IntPtr h=OpenProcess(0x101000,false,pid);if(h==IntPtr.Zero)return null;var name=new System.Text.StringBuilder(32768);int size=name.Capacity;if(!QueryFullProcessImageName(h,0,name,ref size)){CloseHandle(h);return null;}if(entries.Count>=512)Dispose();e=new ProcessEntry {Handle=h,Path=Path.GetFullPath(name.ToString())};entries[pid]=e;return e.Path;}public void Dispose(){foreach(var e in entries.Values)CloseHandle(e.Handle);entries.Clear();}}
 sealed class ReloadWatch:IDisposable {readonly Timer timer;int changed;public bool Changed{get{return Thread.VolatileRead(ref changed)!=0;}}public ReloadWatch(IntPtr handle,string identity,CancellationToken stop){timer=new Timer(s=>{if(stop.IsCancellationRequested){Interlocked.Exchange(ref changed,1);WinDivertShutdown(handle,1);return;}try{if(TestMode&&File.Exists(Core.PathOf("exclusion-worker-fault.test"))){File.Delete(Core.PathOf("exclusion-worker-fault.test"));Interlocked.Exchange(ref testFault,1);Interlocked.Exchange(ref changed,1);WinDivertShutdown(handle,1);return;}if(Exclusions.Identity(Exclusions.Load())!=identity){Interlocked.Exchange(ref changed,1);WinDivertShutdown(handle,1);}}catch(IOException){}catch(Exception e){Log("config watcher: "+e.Message);}},null,100,100);}public void Dispose(){using(var done=new ManualResetEvent(false)){timer.Dispose(done);done.WaitOne();}}}
 internal static void Initialize(){SetDllDirectory(Core.Root);}
 static bool Valid(IntPtr h){return h!=IntPtr.Zero&&h!=new IntPtr(-1);}
 public static string ProcessPath(int pid){IntPtr p=OpenProcess(0x1000,false,pid);if(p==IntPtr.Zero)return null;try{var b=new System.Text.StringBuilder(32768);int size=b.Capacity;return QueryFullProcessImageName(p,0,b,ref size)?Path.GetFullPath(b.ToString()):null;}finally{CloseHandle(p);}}
 static int Port(IntPtr p,int offset){return (Marshal.ReadByte(p,offset)<<8)|Marshal.ReadByte(p,offset+1);}
 static string Address(IntPtr p,int offset,int count){var b=new byte[count];Marshal.Copy(IntPtr.Add(p,offset),b,0,count);return new IPAddress(b).ToString();}
 public static int Owner(bool tcp,int family,string local,int port,string remote,int remotePort){int size=0;uint code=tcp?GetExtendedTcpTable(IntPtr.Zero,ref size,false,family,5,0):GetExtendedUdpTable(IntPtr.Zero,ref size,false,family,1,0);if(code!=122&&code!=0)throw new System.ComponentModel.Win32Exception((int)code);if(size<4)return 0;IntPtr p=Marshal.AllocHGlobal(size);try{code=tcp?GetExtendedTcpTable(p,ref size,false,family,5,0):GetExtendedUdpTable(p,ref size,false,family,1,0);if(code!=0)throw new System.ComponentModel.Win32Exception((int)code);int count=Marshal.ReadInt32(p),owner=0;int stride=tcp?(family==2?24:56):(family==2?12:28);for(int n=0;n<count;n++){IntPtr row=IntPtr.Add(p,4+n*stride);int addr=tcp&&family==2?4:0;int po=tcp?(family==2?8:20):(family==2?4:20);if(Port(row,po)!=port)continue;string a=Address(row,addr,family==2?4:16);if(a!=local&&(tcp||(a!="0.0.0.0"&&a!="::")))continue;if(tcp&&(Address(row,family==2?12:24,family==2?4:16)!=remote||Port(row,family==2?16:44)!=remotePort))continue;int pid=Marshal.ReadInt32(row,stride-4);if(owner!=0&&owner!=pid)return 0;owner=pid;}return owner;}finally{Marshal.FreeHGlobal(p);}}
 public static bool Tuple(byte[] packet,int length,bool outbound,out bool tcp,out int family,out string local,out int port,out string remote,out int remotePort){tcp=false;family=2;local=remote=null;port=remotePort=0;if(length<20)return false;int v=packet[0]>>4,offset,protocol;byte[] a,b;if(v==4){offset=(packet[0]&15)*4;if(offset<20||length<offset+4||(packet[6]&31)!=0||packet[7]!=0)return false;protocol=packet[9];a=packet.Skip(12).Take(4).ToArray();b=packet.Skip(16).Take(4).ToArray();}else if(v==6){family=23;if(length<44)return false;offset=40;protocol=packet[6];a=packet.Skip(8).Take(16).ToArray();b=packet.Skip(24).Take(16).ToArray();for(int n=0;n<8&&(protocol==0||protocol==43||protocol==60||protocol==51);n++){if(length<offset+2)return false;int next=packet[offset],ext=protocol==51?(packet[offset+1]+2)*4:(packet[offset+1]+1)*8;offset+=ext;protocol=next;}if(length<offset+4)return false;}else return false;if(protocol!=6&&protocol!=17)return false;tcp=protocol==6;string source=new IPAddress(a).ToString(),destination=new IPAddress(b).ToString();int sp=(packet[offset]<<8)|packet[offset+1],dp=(packet[offset+2]<<8)|packet[offset+3];local=outbound?source:destination;remote=outbound?destination:source;port=outbound?sp:dp;remotePort=outbound?dp:sp;return true;}
 public static void Run(CancellationToken stop,Action startup=null){
  Initialize();var health=new ExclusionHealth {PID=Process.GetCurrentProcess().Id};int publishing=0;
  var heartbeat=new Timer(_=>{if(Interlocked.Exchange(ref publishing,1)!=0)return;try{Publish(health);}catch(Exception e){Log("status write: "+e.Message);}finally{Interlocked.Exchange(ref publishing,0);}},null,500,500);
  try{while(!stop.IsCancellationRequested){
   var c=Exclusions.Load();string identity=Exclusions.Identity(c);long revision=File.Exists(Core.PathOf("app-exclusions.json"))?File.GetLastWriteTimeUtc(Core.PathOf("app-exclusions.json")).Ticks:0;
   lock(health){health.Ready=false;health.RequestId=identity;health.Revision=revision;health.Error="";health.Warning="";}
   if(!c.Enabled||(c.Applications??new string[0]).Length==0){lock(health)health.Ready=true;SafePublish(health);if(startup!=null){startup();startup=null;}stop.WaitHandle.WaitOne(200);continue;}
   IntPtr capture=WinDivertOpen(TestMode?"outbound and ip.DstAddr == 192.0.2.123 and ((udp and udp.DstPort == 43999) or (tcp and tcp.DstPort == 43998))":"(tcp or udp) and !loopback and !impostor",0,TestMode?(short)29000:(short)30000,0);if(!Valid(capture))throw new System.ComponentModel.Win32Exception(Marshal.GetLastWin32Error());IntPtr bypass=IntPtr.Zero;
   try{
    bypass=WinDivertOpen("false",0,-30000,8);if(!Valid(bypass))throw new System.ComponentModel.Win32Exception(Marshal.GetLastWin32Error());lock(health)health.Ready=true;SafePublish(health);if(startup!=null){startup();startup=null;}
    using(var paths=new ProcessPaths())using(var watcher=new ReloadWatch(capture,identity,stop)){
     byte[] packet=new byte[65575],address=new byte[80];
     while(!stop.IsCancellationRequested&&!watcher.Changed){
      uint length;if(!WinDivertRecv(capture,packet,(uint)packet.Length,out length,address)){if(watcher.Changed||stop.IsCancellationRequested)break;throw new System.ComponentModel.Win32Exception(Marshal.GetLastWin32Error());}
      bool selected=false;
      try{bool tcp;int family,port,rp;string local,remote;if(Tuple(packet,(int)length,(address[10]&2)!=0,out tcp,out family,out local,out port,out remote,out rp)){int pid=Owner(tcp,family,local,port,remote,rp);selected=pid!=0&&Exclusions.Matches(c,paths.Get(pid));}}catch(Exception e){lock(health)health.Warning="Не удалось определить владельца пакета: "+e.Message;}
      uint sent;if(!WinDivertSend(selected?bypass:capture,packet,length,out sent,address)){if(!WinDivertSend(capture,packet,length,out sent,address))throw new System.ComponentModel.Win32Exception(Marshal.GetLastWin32Error());selected=false;lock(health)health.Warning="Пакет отправлен обычным путём: отправка в обход не удалась";}
      if(selected)Interlocked.Increment(ref health.Bypassed);else Interlocked.Increment(ref health.Processed);
     }
     lock(health)health.Ready=false;
     uint queued;WinDivertShutdown(capture,1);while(WinDivertRecv(capture,packet,(uint)packet.Length,out queued,address)){uint sent;WinDivertSend(capture,packet,queued,out sent,address);}if(Interlocked.Exchange(ref testFault,0)!=0)throw new IOException("test injected worker fault");
    }
   }finally{if(Valid(bypass))WinDivertClose(bypass);WinDivertClose(capture);}
  }}catch(Exception e){lock(health){health.Ready=false;health.Error=e.Message;}SafePublish(health);Log(e.ToString());throw;}
  finally{using(var ended=new ManualResetEvent(false)){heartbeat.Dispose(ended);ended.WaitOne();}lock(health)health.Ready=false;SafePublish(health);}
 }
 internal static void Log(string text){try{File.AppendAllText(Core.PathOf("exclusions-service.log"),DateTime.UtcNow.ToString("o")+" "+text+Environment.NewLine);}catch{}}
 static void SafePublish(ExclusionHealth h){try{Publish(h);}catch(Exception e){Log("status write: "+e.Message);}}
 static void Publish(ExclusionHealth h){ExclusionHealth copy;lock(h){copy=new ExclusionHealth {Revision=h.Revision,PID=h.PID,RequestId=h.RequestId,Bypassed=Interlocked.Read(ref h.Bypassed),Processed=Interlocked.Read(ref h.Processed),Ready=h.Ready,Error=h.Error,Warning=h.Warning,Updated=DateTime.UtcNow.ToString("o")};}Core.Write(Core.PathOf("app-exclusions-status.json"),copy);}
}
}