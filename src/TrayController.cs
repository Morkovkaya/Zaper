using System;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.Runtime.InteropServices;
using System.Windows.Forms;
namespace ZapretManager {
public sealed class TrayController:IDisposable {
 [DllImport("user32.dll")]static extern bool DestroyIcon(IntPtr handle);
 readonly Form owner;readonly NotifyIcon tray;readonly ContextMenuStrip menu;
 readonly ToolStripMenuItem status,on,off,restart;
 readonly Icon active,inactive;FormWindowState restored=FormWindowState.Normal;bool disposed,exitRequested;
 public TrayController(Form form,Action<string> service){
  owner=form;active=CreateIcon(Color.FromArgb(52,211,153));inactive=CreateIcon(Color.FromArgb(148,163,184));
  menu=new ContextMenuStrip();status=new ToolStripMenuItem("Zapret 2") {Enabled=false};menu.Items.Add(status);
  menu.Items.Add("Открыть приложение",null,(s,e)=>Open());menu.Items.Add(new ToolStripSeparator());
  on=new ToolStripMenuItem("Включить",null,(s,e)=>service("On"));off=new ToolStripMenuItem("Выключить",null,(s,e)=>service("Off"));restart=new ToolStripMenuItem("Перезапустить",null,(s,e)=>service("Restart"));
  menu.Items.AddRange(new ToolStripItem[]{on,off,restart,new ToolStripSeparator()});
  menu.Items.Add("Выйти из приложения",null,(s,e)=>Exit());
  tray=new NotifyIcon {Icon=inactive,Text="Zapret 2",ContextMenuStrip=menu,Visible=true};
  tray.MouseClick+=(s,e)=>{if(e.Button==MouseButtons.Left)Open();};
  owner.Resize+=Resized;owner.FormClosed+=(s,e)=>Dispose();owner.Icon=inactive;
 }
 static Icon CreateIcon(Color color){using(var bitmap=new Bitmap(32,32)){using(var g=Graphics.FromImage(bitmap)){g.SmoothingMode=SmoothingMode.AntiAlias;g.Clear(Color.Transparent);using(var b=new SolidBrush(Color.FromArgb(15,23,42)))g.FillEllipse(b,1,1,30,30);using(var p=new Pen(color,3))g.DrawEllipse(p,3,3,26,26);using(var font=new Font("Segoe UI",16,FontStyle.Bold,GraphicsUnit.Pixel))using(var brush=new SolidBrush(color))using(var format=new StringFormat {Alignment=StringAlignment.Center,LineAlignment=StringAlignment.Center})g.DrawString("Z",font,brush,new RectangleF(0,0,32,32),format);}IntPtr handle=bitmap.GetHicon();try{using(var icon=Icon.FromHandle(handle))return (Icon)icon.Clone();}finally{DestroyIcon(handle);}}}
 void Resized(object sender,EventArgs e){if(disposed)return;if(owner.WindowState==FormWindowState.Minimized)owner.Hide();else restored=owner.WindowState;}
 public void Open(){if(disposed||owner.IsDisposed)return;owner.Show();owner.WindowState=restored;owner.BringToFront();owner.Activate();}
 public bool HideOnClose(FormClosingEventArgs e){if(!exitRequested&&e.CloseReason==CloseReason.UserClosing){e.Cancel=true;owner.Hide();return true;}return false;}
 public void Exit(){if(disposed)return;exitRequested=true;owner.Close();if(!owner.IsDisposed)exitRequested=false;}
 public bool Released {get{return disposed;}}
 public void Refresh(string state,bool busy){if(disposed)return;bool running=state=="Running";string text=running?"Zapret включён":state=="Stopped"?"Zapret выключен":state=="NotInstalled"?"Служба не установлена":"Состояние: "+state;status.Text=text;tray.Text="Zapret 2 — "+(busy?"выполняется операция":text);tray.Icon=running?active:inactive;owner.Icon=tray.Icon;on.Enabled=!busy&&state=="Stopped";off.Enabled=restart.Enabled=!busy&&running;}
 public bool Test(){
  Refresh("Running",false);bool started=!on.Enabled&&off.Enabled&&restart.Enabled&&tray.Visible;
  Refresh("Stopped",false);bool stopped=on.Enabled&&!off.Enabled&&!restart.Enabled;
  Refresh("Running",true);bool locked=!on.Enabled&&!off.Enabled&&!restart.Enabled;
  owner.WindowState=FormWindowState.Minimized;Application.DoEvents();bool hidden=!owner.Visible&&tray.Visible;
  Open();Application.DoEvents();bool restoredWindow=owner.Visible&&owner.WindowState!=FormWindowState.Minimized;
  owner.Close();Application.DoEvents();bool closeHidden=!owner.IsDisposed&&!owner.Visible&&tray.Visible;
  Open();Application.DoEvents();return started&&stopped&&locked&&hidden&&restoredWindow&&closeHidden&&owner.Visible;
 }
 public void Dispose(){if(disposed)return;disposed=true;owner.Resize-=Resized;tray.Visible=false;tray.Dispose();menu.Dispose();active.Dispose();inactive.Dispose();}
}
}
