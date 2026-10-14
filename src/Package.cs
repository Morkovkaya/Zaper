using System;
using System.IO;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Win32;
namespace ZapretManager {
public static class Package {
 public static void Prepare(){Core.Guard();using(var k=Registry.LocalMachine.OpenSubKey(@"SYSTEM\CurrentControlSet\Services\zapret2")){if(k!=null&&ServicePaths.AtRoot((string)k.GetValue("ImagePath",""))){bool running=Core.State()=="Running";Core.Write(Core.PathOf("package-upgrade-state.json"),running);if(Core.State()!="Stopped")Core.Control("Off");Core.StopOrphanEngine();}}Exclusions.Stop();}
 public static async Task TestService(){string[] files={"manager-base.txt","config.txt","manager-settings.json"};byte[][] old=new byte[files.Length][];for(int i=0;i<files.Length;i++)old[i]=File.ReadAllBytes(Core.PathOf(files[i]));string service=Core.Service;Core.Service="zapret2-installer-test";try{if(Core.State()!="NotInstalled")throw new Exception("Тестовая служба уже существует");File.WriteAllText(Core.PathOf("manager-base.txt"),"--wf-tcp-out=1\r\n--filter-tcp=1\r\n",System.Text.Encoding.ASCII);Core.Write(Core.PathOf("manager-settings.json"),new Settings {Game="off",IPSet="none",AutoStart=false});await Core.Install(CancellationToken.None);Core.Control("Restart");await Core.Remove(CancellationToken.None);File.WriteAllText(Core.PathOf("package-service-test.txt"),"PASS: packaged engine service create/start/restart/remove, isolated TCP port 1\r\n");}finally{if(Core.State()!="NotInstalled")awaitRemove();Core.Service=service;for(int i=0;i<files.Length;i++)File.WriteAllBytes(Core.PathOf(files[i]),old[i]);}}
 static void awaitRemove(){Core.Remove(CancellationToken.None).GetAwaiter().GetResult();}
 public static async Task Configure(){
  Core.Preflight();
  string template=Core.PathOf("manager-base.template");
  if(!File.Exists(Core.PathOf("manager-base.txt")))File.WriteAllText(Core.PathOf("manager-base.txt"),File.ReadAllText(template).Replace("%ROOT%",Core.Root),System.Text.Encoding.ASCII);
  if(!File.Exists(Core.PathOf("manager-settings.json")))Core.Write(Core.PathOf("manager-settings.json"),new Settings {Game="udp",IPSet="loaded",AutoStart=true});
  string text=Core.Build(Core.Load());await Core.Validate(text,CancellationToken.None);
  if(!File.Exists(Core.PathOf("config.txt")))File.WriteAllText(Core.PathOf("config.txt"),text+"\r\n",System.Text.Encoding.ASCII);
  if(Array.IndexOf(Environment.GetCommandLineArgs(),"--install-service")>=0)await Core.Install(CancellationToken.None);
  string resume=Core.PathOf("package-upgrade-state.json");if(File.Exists(resume)){bool running=Core.Read<bool>(resume);if(running&&Core.State()!="NotInstalled")Core.Control("On");File.Delete(resume);}
  File.WriteAllText(Core.PathOf("package-status.txt"),"PASS: configuration verified; root="+Core.Root+"\r\n");
 }
 public static async Task Remove(){
  using(var key=Registry.LocalMachine.OpenSubKey(@"SYSTEM\CurrentControlSet\Services\zapret2")){if(key!=null){string image=(string)key.GetValue("ImagePath","");if(ServicePaths.AtRoot(image))await Core.Remove(CancellationToken.None);}}
  if(File.Exists(Core.PathOf("vpn-upload-state.json"))){Relay.Off();await Task.Delay(1500);}
  await Exclusions.Remove();
 }
}
}
