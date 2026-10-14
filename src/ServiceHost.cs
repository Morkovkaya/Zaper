using System;
using System.IO;
using System.Diagnostics;
using System.Runtime.InteropServices;
using System.ServiceProcess;
using System.Threading;
using System.Threading.Tasks;
using System.Text;
using System.Text.RegularExpressions;
namespace ZapretManager {
public class EngineHealth {public int PID;public bool Ready;public string Error="",Updated;}
public sealed class EngineService:ServiceBase {
 Process engine;IntPtr job;readonly object logLock=new object();
 [DllImport("kernel32.dll",CharSet=CharSet.Unicode)]static extern IntPtr CreateJobObject(IntPtr attributes,string name);
 [DllImport("kernel32.dll",SetLastError=true)]static extern bool SetInformationJobObject(IntPtr job,int type,IntPtr data,int size);
 [DllImport("kernel32.dll",SetLastError=true)]static extern bool AssignProcessToJobObject(IntPtr job,IntPtr process);
 [DllImport("kernel32.dll")]static extern bool CloseHandle(IntPtr handle);
 public EngineService(string name){ServiceName=name;CanStop=true;CanShutdown=true;}
 string StatusFile{get{return Core.PathOf(ServiceName+"-engine-status.json");}}
 void Status(bool ready,string error){Core.Write(StatusFile,new EngineHealth {PID=engine==null?0:engine.Id,Ready=ready,Error=error,Updated=DateTime.UtcNow.ToString("o")});}
 void Log(string text){if(text==null)return;lock(logLock){try{File.AppendAllText(Core.PathOf("engine-service.log"),DateTime.Now.ToString("o")+" "+text+Environment.NewLine);}catch{}}}
 protected override void OnStart(string[] args){RequestAdditionalTime(60000);try{
  Core.Preflight();string text=File.ReadAllText(Core.PathOf("config.txt"));
  job=CreateJobObject(IntPtr.Zero,null);if(job==IntPtr.Zero)throw new System.ComponentModel.Win32Exception();IntPtr data=Marshal.AllocHGlobal(144);try{for(int n=0;n<144;n++)Marshal.WriteByte(data,n,0);Marshal.WriteInt32(data,16,0x2000);if(!SetInformationJobObject(job,9,data,144))throw new System.ComponentModel.Win32Exception();}finally{Marshal.FreeHGlobal(data);}
  engine=new Process {StartInfo=new ProcessStartInfo(Core.PathOf("winws2.exe"),Regex.Replace(text,@"\r?\n"," ")){UseShellExecute=false,CreateNoWindow=true,WorkingDirectory=Core.Root,RedirectStandardOutput=true,RedirectStandardError=true}};
  engine.OutputDataReceived+=(s,e)=>Log(e.Data);engine.ErrorDataReceived+=(s,e)=>Log(e.Data);engine.Start();if(!AssignProcessToJobObject(job,engine.Handle))throw new System.ComponentModel.Win32Exception();engine.BeginOutputReadLine();engine.BeginErrorReadLine();Status(false,"");
  ExclusionWorker.Initialize();IntPtr reflect=ExclusionWorker.WinDivertOpen("processId == "+engine.Id,4,0,5);if(reflect==new IntPtr(-1))throw new System.ComponentModel.Win32Exception(Marshal.GetLastWin32Error());bool ready=false;try{using(var timeout=new Timer(s=>ExclusionWorker.WinDivertShutdown(reflect,1),null,45000,Timeout.Infinite)){byte[] packet=new byte[65575],address=new byte[80];uint length;while(ExclusionWorker.WinDivertRecv(reflect,packet,(uint)packet.Length,out length,address)){if(BitConverter.ToInt32(address,28)==0){ready=true;break;}}}}finally{ExclusionWorker.WinDivertClose(reflect);}if(!ready||engine.HasExited)throw new Exception(engine.HasExited?"winws2 завершился (exit="+engine.ExitCode+"). См. engine-service.log":"winws2 не открыл сетевой фильтр за 45 секунд. См. engine-service.log");
  Status(true,"");engine.EnableRaisingEvents=true;engine.Exited+=(s,e)=>{try{Status(false,"winws2 завершился (exit="+engine.ExitCode+")");ThreadPool.QueueUserWorkItem(_=>{try{Stop();}catch{}});}catch{}};
 }catch(Exception e){try{Status(false,e.Message);}catch{}Cleanup();throw;}}
 void Cleanup(){if(job!=IntPtr.Zero){CloseHandle(job);job=IntPtr.Zero;}if(engine!=null){try{if(!engine.HasExited)engine.Kill();engine.WaitForExit(5000);}catch{}engine.Dispose();engine=null;}}
 protected override void OnStop(){RequestAdditionalTime(10000);if(engine!=null)engine.EnableRaisingEvents=false;Cleanup();Status(false,"");}
 protected override void OnShutdown(){OnStop();}
}
public static class ServicePaths {
 public static string Host{get{return Core.PathOf("app\\Zapret2Service.exe");}}
 public static string Executable(string image){image=Environment.ExpandEnvironmentVariables(image??"").Trim();if(image.StartsWith("\"")){int end=image.IndexOf('"',1);return end>1?image.Substring(1,end-1):"";}int split=image.IndexOf(".exe",StringComparison.OrdinalIgnoreCase);return split>=0?image.Substring(0,split+4):"";}
 public static bool Known(string image,bool engine){string exe=Executable(image),file=Path.GetFileName(exe);return engine?string.Equals(file,"winws2.exe",StringComparison.OrdinalIgnoreCase)||string.Equals(file,"Zapret2Service.exe",StringComparison.OrdinalIgnoreCase)&&image.Contains("--engine-service"):string.Equals(file,"Zapret2Manager.exe",StringComparison.OrdinalIgnoreCase)&&image.Contains("--exclusion-service")||string.Equals(file,"Zapret2Service.exe",StringComparison.OrdinalIgnoreCase)&&image.Contains("--exclusion-service");}
 public static bool AtRoot(string image){string p=Executable(image);return p!=""&&Path.GetFullPath(p).StartsWith(Path.GetFullPath(Core.Root)+Path.DirectorySeparatorChar,StringComparison.OrdinalIgnoreCase);}
}
}
