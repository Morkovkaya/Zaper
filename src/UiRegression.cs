using System;
using System.IO;
using System.Linq;
using System.Drawing;
using System.Collections.Generic;
using System.Threading.Tasks;
using System.Windows.Forms;
namespace ZapretManager {
public static class UiRegression {
 static IEnumerable<Control> All(Control parent){foreach(Control c in parent.Controls){yield return c;foreach(var child in All(c))yield return child;}}
 public static Task<int> Run(){
  string directory=Path.Combine(AppDomain.CurrentDomain.BaseDirectory,"tests");Directory.CreateDirectory(directory);var report=new List<string>();int failures=0;
  Action<bool,string> check=(ok,name)=>{report.Add((ok?"PASS: ":"FAIL: ")+name);if(!ok)failures++;};
  var form=new MainForm();form.Shown+=async(s,e)=>{try{
   check(form.Text=="Zaper 3.8.1","short zaper window title");
   check(!All(form).OfType<Button>().Any(b=>b.Text.Contains("Настроить FACEIT")||b.Text=="График задержки"),"no duplicate FACEIT shortcut or separate graph launcher");
   check(All(form).OfType<LatencyPanel>().Count()==1,"graph embedded directly in diagnostics");
   check(await form.NetworkGraph.TestLocal(),"embedded diagnostics graph plots real loopback samples");
   check(await ParallelDownload(),"UI stays responsive while direct download cancels stalled proxy route");
   check(!All(form).OfType<Button>().Any(b=>b.Text.Contains("Обновить Hosts"))&&All(form).OfType<Button>().Any(b=>b.Text=="Hosts"),"Hosts editor entry replaces misleading update button");
   using(var servers=new FaceForm()){var buttons=All(servers).OfType<Button>().ToArray();check(buttons.Length==1&&buttons[0].Text=="Проверить","server window has only the requested check action");}
   using(var preferences=new PreferencesForm(()=>{})){check(preferences.Text=="Настройки запуска и трея","launch and tray window has requested title");check(!All(preferences).OfType<Label>().Any(l=>l.Text.Contains("Крестик")),"tray settings omit redundant close hint");check(All(preferences).OfType<CheckBox>().Count()==4,"panel, service, hidden startup and error options have descriptions");}
   using(var excluded=new ExclusionForm()){check(excluded.Text=="Zaper — исключения приложений","exclusions title uses capital Zaper without 2");}
   using(var about=new AboutForm()){check(about.Text=="О Zaper"&&All(about).OfType<Label>().Any(l=>l.Text=="Zaper"),"About window uses capital Zaper");}
   using(var picker=new AppPicker(p=>{})){picker.Show(form);Application.DoEvents();check(picker.TestIconsAndSelection(),"EXE icons display and selection survives filtering");picker.Close();}
   form.SelectPage(1);check(All(form).OfType<Button>().Any(b=>b.Text=="Настройки запуска и трея"&&b.Visible),"launch/tray entry is on Settings page");form.SelectPage(3);check(!All(form).OfType<Button>().Any(b=>b.Text=="Настройки запуска и трея"&&b.Visible),"launch/tray entry removed from Maintenance");form.SelectPage(0);
   check(typeof(MainForm).GetMethod("Confirm")==null,"manual Discord confirmation removed");
   using(var graph=new LatencyForm()){bool passed=await graph.TestLocal();File.WriteAllText(Path.Combine(directory,"graph-test.txt"),(passed?"PASS":"FAIL")+": loopback ping samples plotted, counter updates, graph disposal");check(passed,"live graph loopback samples");}
   string root=Core.Root;string fixture=Path.Combine(directory,"startup-fixture");Directory.CreateDirectory(fixture);
   try{Core.Root=fixture;Core.Write(Core.PathOf("ui-preferences.json"),new UiPreferences {StartInTray=true});Program.TestStartupPreferences=true;using(var hidden=new MainForm()){hidden.Show();Application.DoEvents();check(hidden.StartedHidden,"saved StartInTray preference suppresses initial window");check(hidden.TestTray(),"initially hidden window restores and closes to tray");hidden.ExitApp();}Program.TestStartupPreferences=false;}finally{Core.Root=root;Program.TestStartupPreferences=false;}
   bool tray=form.TestTray();File.WriteAllText(Path.Combine(directory,"tray-test.txt"),(tray?"PASS":"FAIL")+": status/menu states, operation lock, minimize/cross hide and restore");check(tray,"tray lifecycle");
   Tests.Preview(form);Tests.PreviewExclusions();check(File.ReadAllText(Path.Combine(directory,"layout-test.txt")).Contains("Failures: 0"),"all pages fit default and minimum sizes");
  }catch(Exception ex){check(false,ex.ToString());}finally{form.ExitApp();check(form.IsDisposed&&form.TrayReleased,"explicit exit closes form and removes tray icon");File.AppendAllText(Path.Combine(directory,"tray-test.txt"),Environment.NewLine+(form.IsDisposed&&form.TrayReleased?"PASS":"FAIL")+": explicit exit closes form and removes tray icon");report.Add("Failures: "+failures);File.WriteAllLines(Path.Combine(directory,"ui-test.txt"),report);}};
  Application.Run(form);return Task.FromResult(failures==0?0:1);
 }
 static async Task<bool> ParallelDownload(){
  var direct=new System.Net.Sockets.TcpListener(System.Net.IPAddress.Loopback,0);var proxy=new System.Net.Sockets.TcpListener(System.Net.IPAddress.Loopback,0);direct.Start();proxy.Start();int beats=0;
  using(var timer=new System.Windows.Forms.Timer {Interval=25}){timer.Tick+=(s,e)=>beats++;timer.Start();try{
   var good=Task.Run(async()=>{using(var peer=await direct.AcceptTcpClientAsync()){var stream=peer.GetStream();var buffer=new byte[4096];await stream.ReadAsync(buffer,0,buffer.Length);await Task.Delay(150);byte[] data=System.Text.Encoding.ASCII.GetBytes("HTTP/1.1 200 OK\r\nContent-Length: 11\r\nConnection: close\r\n\r\n1.2.3.0/24\n");await stream.WriteAsync(data,0,data.Length);}});
   var slow=Task.Run(async()=>{using(var peer=await proxy.AcceptTcpClientAsync()){await Task.Delay(1000);}});
   string value=await Downloads.FetchRoutes("http://127.0.0.1:"+((System.Net.IPEndPoint)direct.LocalEndpoint).Port+"/list",new[]{null,"127.0.0.1:"+((System.Net.IPEndPoint)proxy.LocalEndpoint).Port},System.Threading.CancellationToken.None);await Task.WhenAll(good,slow);return Core.ValidateIPSet(value)==1&&beats>0;
  }finally{timer.Stop();direct.Stop();proxy.Stop();}}
 }
}
}
