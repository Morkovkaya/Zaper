using System;
using System.IO;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using System.Collections.Generic;
using Microsoft.Win32;
namespace ZapretManager {
public static class RepairTests {
 public static async Task<int> Run(string report){var lines=new List<string>();int failures=0;Action<bool,string> check=(ok,name)=>{lines.Add((ok?"PASS: ":"FAIL: ")+name);if(!ok)failures++;File.WriteAllLines(report,lines);};string service=Core.Service,helper=Exclusions.ServiceName;string[] files={"manager-base.txt","config.txt","manager-settings.json"};byte[][] old=files.Select(f=>File.ReadAllBytes(Core.PathOf(f))).ToArray();string copy=Core.PathOf("app\\copied-manager.exe");try{
  Core.Preflight();check(true,"complete packaged native runtime passes SHA256 preflight");string dll=Core.PathOf("cygwin1.dll"),moved=dll+".test-backup";File.Move(dll,moved);try{bool missing=false;try{Core.Preflight();}catch(FileNotFoundException e){missing=e.Message.Contains("cygwin1.dll");}check(missing,"missing Cygwin produces actionable filename instead of service timeout");}finally{File.Move(moved,dll);}
  File.Move(dll,moved);try{File.WriteAllBytes(dll,new byte[]{1,2,3});bool bad=false;try{Core.Preflight();}catch(InvalidOperationException e){bad=e.Message.Contains("cygwin1.dll");}check(bad,"corrupt/incompatible Cygwin detected before engine starts");}finally{File.Delete(dll);File.Move(moved,dll);}
  Core.Service="zapret2-repair-test";Exclusions.ServiceName="zapret2-repair-helper-test";Exclusions.Testing=true;
  if(Core.State()!="NotInstalled"||Exclusions.State()!="NotInstalled")throw new Exception("Repair test services already exist");
  File.WriteAllText(Core.PathOf("manager-base.txt"),"--wf-tcp-out=1\r\n--filter-tcp=1\r\n",System.Text.Encoding.ASCII);Core.Write(Core.PathOf("manager-settings.json"),new Settings {Game="off",IPSet="none",AutoStart=false});
  string exe=System.Reflection.Assembly.GetExecutingAssembly().Location;Core.CreateAuxService(Exclusions.ServiceName,Core.Quote(exe)+" --exclusion-service "+Exclusions.ServiceName);
  await Core.Install(CancellationToken.None);check(Core.State()=="Running","cold engine starts as managed child without manually opened winws2");
  using(var key=Registry.LocalMachine.OpenSubKey(@"SYSTEM\CurrentControlSet\Services\"+Exclusions.ServiceName)){check(ServicePaths.Executable((string)key.GetValue("ImagePath"))==ServicePaths.Host,"legacy exclusion helper repaired to canonical service executable");}
  Core.Control("Off");Core.ConfigureService(Core.Service,Core.Quote(Core.PathOf("winws2.exe"))+" --wf-tcp-out=1 --filter-tcp=1");Core.Control("On");check(Core.State()=="Running","legacy direct winws service migrates through SCM API and starts cold");
  for(int n=0;n<3;n++){Core.Control("Restart");check(Core.State()=="Running","restart cycle "+(n+1)+" cleans up previous engine process");}
  File.Copy(exe,copy,true);var result=await Core.Run(copy,"--test-canonical-helper",CancellationToken.None,30000);check(result.Exit==0,"launching another copy of Manager does not report foreign helper ownership");
  Core.Control("Off");Core.ConfigureService(Exclusions.ServiceName,start:4);Core.Control("On");check(Exclusions.State()=="Running","disabled helper recovers when zapret is enabled");
  Core.Control("Off");var p=System.Diagnostics.Process.GetProcessesByName("winws2");check(!p.Any(x=>{try{return string.Equals(x.MainModule.FileName,Core.PathOf("winws2.exe"),StringComparison.OrdinalIgnoreCase);}catch{return false;}finally{x.Dispose();}}),"stopping service leaves no orphan winws2 in test installation");
 }catch(Exception e){check(false,e.ToString());}finally{try{if(Core.Service=="zapret2-repair-test"&&Core.State()!="NotInstalled")Core.Remove(CancellationToken.None).GetAwaiter().GetResult();if(Exclusions.ServiceName=="zapret2-repair-helper-test")Exclusions.Remove().GetAwaiter().GetResult();}catch(Exception e){check(false,"cleanup: "+e.Message);}Core.Service=service;Exclusions.ServiceName=helper;Exclusions.Testing=false;for(int n=0;n<files.Length;n++)File.WriteAllBytes(Core.PathOf(files[n]),old[n]);if(File.Exists(copy))File.Delete(copy);}lines.Add("Failures: "+failures);File.WriteAllLines(report,lines);return failures==0?0:1;
 }
}
}
