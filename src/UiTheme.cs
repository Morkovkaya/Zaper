using System;
using System.Drawing;
using System.Windows.Forms;
namespace ZapretManager {
public static class UiTheme {
 static readonly Icon ApplicationIcon=TrayController.CreateIcon(Color.FromArgb(52,211,153));
 public static readonly Color Background=Color.FromArgb(15,23,42),Surface=Color.FromArgb(30,41,59),Accent=Color.FromArgb(59,130,246),Text=Color.FromArgb(226,232,240),Muted=Color.FromArgb(148,163,184);
 public static void Apply(Control root) {
  root.Font=new Font("Segoe UI",10);root.ForeColor=Text;
  if(root is Form){root.BackColor=Background;((Form)root).Icon=ApplicationIcon;}
  foreach(Control c in root.Controls){Apply(c);
   var b=c as Button;if(b!=null){b.FlatStyle=FlatStyle.Flat;b.FlatAppearance.BorderSize=0;b.BackColor=Surface;b.ForeColor=Text;b.Padding=new Padding(12,4,12,4);b.MinimumSize=new Size(0,40);b.Cursor=Cursors.Hand;b.FlatAppearance.MouseOverBackColor=Color.FromArgb(51,65,85);b.FlatAppearance.MouseDownBackColor=Accent;}
   var t=c as TextBox;if(t!=null){t.BackColor=Surface;t.ForeColor=Text;t.BorderStyle=BorderStyle.FixedSingle;}
   var l=c as ListBox;if(l!=null){l.BackColor=Surface;l.ForeColor=Text;l.BorderStyle=BorderStyle.None;l.ItemHeight=26;}
   var combo=c as ComboBox;if(combo!=null){combo.BackColor=Surface;combo.ForeColor=Text;combo.FlatStyle=FlatStyle.Flat;combo.DrawMode=DrawMode.OwnerDrawFixed;combo.ItemHeight=27;combo.DrawItem+=(s,e)=>{e.DrawBackground();if(e.Index>=0){string value=Convert.ToString(combo.Items[e.Index]);if(combo.Name=="game")value=value=="off"?"Выключен":value=="udp"?"Игры (UDP)":value=="tcp"?"TCP":"TCP и UDP";if(combo.Name=="ips")value=value=="none"?"Без списка":value=="loaded"?"По списку адресов":"Все адреса";TextRenderer.DrawText(e.Graphics,value,combo.Font,e.Bounds,Text,TextFormatFlags.Left|TextFormatFlags.VerticalCenter|TextFormatFlags.EndEllipsis);}e.DrawFocusRectangle();};}
   var grid=c as DataGridView;if(grid!=null){grid.BackgroundColor=Background;grid.BorderStyle=BorderStyle.None;grid.CellBorderStyle=DataGridViewCellBorderStyle.SingleHorizontal;grid.GridColor=Surface;grid.RowHeadersVisible=false;grid.EnableHeadersVisualStyles=false;grid.ColumnHeadersHeight=42;grid.ColumnHeadersHeightSizeMode=DataGridViewColumnHeadersHeightSizeMode.DisableResizing;grid.ColumnHeadersDefaultCellStyle.BackColor=Surface;grid.ColumnHeadersDefaultCellStyle.ForeColor=Text;grid.DefaultCellStyle.BackColor=Background;grid.DefaultCellStyle.ForeColor=Text;grid.DefaultCellStyle.SelectionBackColor=Color.FromArgb(30,64,100);grid.DefaultCellStyle.SelectionForeColor=Color.White;grid.AlternatingRowsDefaultCellStyle.BackColor=Color.FromArgb(20,30,49);grid.RowTemplate.Height=36;grid.DefaultCellStyle.Padding=new Padding(8,4,8,4);}
  }
 }
 public static void Primary(Button button){button.BackColor=Accent;button.ForeColor=Color.White;button.FlatAppearance.MouseOverBackColor=Color.FromArgb(37,99,235);}
}
}
