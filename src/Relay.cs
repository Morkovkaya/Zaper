using System;
using System.IO;
using System.Diagnostics;
using System.Linq;
using System.Net;
using System.Net.Sockets;
using System.Threading;
using System.Threading.Tasks;
using System.Runtime.InteropServices;
using Microsoft.Win32;

namespace ZapretManager {
public sealed class UploadRelay:IDisposable {
 readonly TcpListener listener; readonly CancellationTokenSource stop=new CancellationTokenSource();readonly object gate=new object();readonly double bytesPerSecond;double next;readonly Stopwatch clock=Stopwatch.StartNew();
 public UploadRelay(int port,int rateMbps,int upstreamPort=10809){if(rateMbps<1||rateMbps>1000)throw new ArgumentException("Некорректный лимит");bytesPerSecond=rateMbps*1000000.0/8;listener=new TcpListener(IPAddress.Loopback,port);listener.Start();Accept(upstreamPort);}
 async void Accept(int port){while(!stop.IsCancellationRequested){try{var client=await listener.AcceptTcpClientAsync();Forward(client,port);}catch{if(stop.IsCancellationRequested)break;}}}
 async Task Pace(int count,CancellationToken token){double delay;lock(gate){double now=clock.Elapsed.TotalSeconds;next=Math.Max(next,now-16384.0/bytesPerSecond);delay=Math.Max(0,next-now);next+=count/bytesPerSecond;}if(delay>0)await Task.Delay((int)Math.Ceiling(delay*1000),token);}
 async Task Copy(NetworkStream from,NetworkStream to,bool upload,CancellationToken token){byte[] b=new byte[8192];while(!token.IsCancellationRequested){int n=await from.ReadAsync(b,0,b.Length,token);if(n==0)break;if(upload)await Pace(n,token);await to.WriteAsync(b,0,n,token);}}
 async void Forward(TcpClient client,int port){using(client)using(var upstream=new TcpClient())using(var cancellation=CancellationTokenSource.CreateLinkedTokenSource(stop.Token)){try{client.NoDelay=true;upstream.NoDelay=true;client.ReceiveBufferSize=16384;upstream.SendBufferSize=16384;var connect=upstream.ConnectAsync(IPAddress.Loopback,port);if(await Task.WhenAny(connect,Task.Delay(5000,stop.Token))!=connect)return;await connect;var send=Copy(client.GetStream(),upstream.GetStream(),true,cancellation.Token);var receive=Copy(upstream.GetStream(),client.GetStream(),false,cancellation.Token);await Task.WhenAny(send,receive);cancellation.Cancel();client.Close();upstream.Close();try{await Task.WhenAll(send,receive);}catch{}}catch{}}}
 public void Dispose(){stop.Cancel();listener.Stop();}
}
public class ProxyState {public string ProxyServer;public int ProxyEnable;}
public class RelayLive {public int PID,RateMbps,Port;public string Started;}
public static class Relay {
 const string Key=@"Software\Microsoft\Windows\CurrentVersion\Internet Settings",RunKey=@"Software\Microsoft\Windows\CurrentVersion\Run";
 [DllImport("wininet.dll")]static extern bool InternetSetOption(IntPtr h,int option,IntPtr buffer,int length);
 static void Notify(){InternetSetOption(IntPtr.Zero,39,IntPtr.Zero,0);InternetSetOption(IntPtr.Zero,37,IntPtr.Zero,0);}
 public static void Recover(){string f=Core.PathOf("vpn-upload-state.json");if(File.Exists(f)){var old=Core.Read<ProxyState>(f);using(var key=Registry.CurrentUser.OpenSubKey(Key,true)){if((string)key.GetValue("ProxyServer","")=="127.0.0.1:10819"){key.SetValue("ProxyServer",old.ProxyServer);key.SetValue("ProxyEnable",old.ProxyEnable);Notify();}}}using(var run=Registry.CurrentUser.OpenSubKey(RunKey,true)){if(run!=null)run.DeleteValue("Zapret2RestoreProxy",false);}}
 public static void Off(){Recover();File.WriteAllText(Core.PathOf("vpn-upload-stop.flag"),"stop");}
 public static Process Child(string args){return Process.Start(new ProcessStartInfo(System.Reflection.Assembly.GetExecutingAssembly().Location,args){UseShellExecute=false,CreateNoWindow=true,WindowStyle=ProcessWindowStyle.Hidden});}
 public static async Task On(int rate,CancellationToken token){string proxy=Core.Proxy();if(proxy=="127.0.0.1:10819")return;if(proxy!="127.0.0.1:10809")throw new Exception("Включите proxy Happ 127.0.0.1:10809");File.Delete(Core.PathOf("vpn-upload-stop.flag"));Core.Write(Core.PathOf("vpn-upload-state.json"),new ProxyState {ProxyEnable=1,ProxyServer=proxy});var p=Child("--relay "+rate);try{var sw=Stopwatch.StartNew();while(!System.Net.NetworkInformation.IPGlobalProperties.GetIPGlobalProperties().GetActiveTcpListeners().Any(x=>x.Port==10819)){token.ThrowIfCancellationRequested();if(p.HasExited||sw.ElapsedMilliseconds>15000)throw new Exception("Ограничитель не запустился");await Task.Delay(100,token);}using(var run=Registry.CurrentUser.CreateSubKey(RunKey)){run.SetValue("Zapret2RestoreProxy",Core.Quote(System.Reflection.Assembly.GetExecutingAssembly().Location)+" --recover-proxy");}using(var key=Registry.CurrentUser.OpenSubKey(Key,true)){key.SetValue("ProxyServer","127.0.0.1:10819");Notify();}}catch{Off();throw;}finally{p.Dispose();}}
 public static void Serve(int rate){using(var mutex=new Mutex(false,@"Local\Zapret2UploadRelay")){bool own=false;try{try{own=mutex.WaitOne(0);}catch(AbandonedMutexException){own=true;}if(!own)return;using(var relay=new UploadRelay(10819,rate)){Core.Write(Core.PathOf("vpn-upload-live.json"),new RelayLive {PID=Process.GetCurrentProcess().Id,RateMbps=rate,Port=10819,Started=DateTime.Now.ToString("o")});Child("--watch "+Process.GetCurrentProcess().Id).Dispose();while(!File.Exists(Core.PathOf("vpn-upload-stop.flag"))){using(var key=Registry.CurrentUser.OpenSubKey(Key,true)){if(Convert.ToInt32(key.GetValue("ProxyEnable",0))==1&&(string)key.GetValue("ProxyServer","")=="127.0.0.1:10809"){key.SetValue("ProxyServer","127.0.0.1:10819");Notify();}}Thread.Sleep(1000);}}}finally{if(own){Recover();mutex.ReleaseMutex();}}}}
 public static void Watch(int pid){try{using(var p=Process.GetProcessById(pid)){p.WaitForExit();}}catch(ArgumentException){}try{var live=Core.Read<RelayLive>(Core.PathOf("vpn-upload-live.json"));if(live.PID==pid)Recover();}catch{}}
}
}
