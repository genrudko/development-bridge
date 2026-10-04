using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Runtime.InteropServices;
using System.Text;

namespace EnergoLogicTopologyRestore
{
    internal sealed class Edge
    {
        public int SourceId;
        public string Endpoint;
        public int TargetId;
        public int Row;
    }

    internal static class Program
    {
        private static string Decode(string value)
        {
            return Encoding.UTF8.GetString(Convert.FromBase64String(value));
        }

        private static int Main(string[] args)
        {
            string resultPath = args.Length > 1 ? args[1] : "";
            try
            {
                if (args.Length != 2)
                    throw new InvalidOperationException("Usage: EnergoLogic.TopologyRestoreHelper.exe <plan> <result>");

                string planPath = args[0];
                string documentName = "";
                string pageName = "";
                List<Edge> edges = new List<Edge>();

                foreach (string raw in File.ReadAllLines(planPath, Encoding.UTF8))
                {
                    if (String.IsNullOrWhiteSpace(raw)) continue;
                    string[] parts = raw.Split('\t');
                    if (parts.Length == 2 && parts[0] == "DOC")
                        documentName = Decode(parts[1]);
                    else if (parts.Length == 2 && parts[0] == "PAGE")
                        pageName = Decode(parts[1]);
                    else if (parts.Length == 5 && parts[0] == "EDGE")
                    {
                        edges.Add(new Edge {
                            SourceId = Int32.Parse(parts[1], CultureInfo.InvariantCulture),
                            Endpoint = parts[2],
                            TargetId = Int32.Parse(parts[3], CultureInfo.InvariantCulture),
                            Row = Int32.Parse(parts[4], CultureInfo.InvariantCulture)
                        });
                    }
                }

                if (String.IsNullOrWhiteSpace(documentName) || String.IsNullOrWhiteSpace(pageName))
                    throw new InvalidOperationException("Topology plan is missing document/page identity");
                if (edges.Count == 0)
                    throw new InvalidOperationException("Topology plan has no edges");

                dynamic app = Marshal.GetActiveObject("Visio.Application");
                dynamic document = null;
                for (int index = 1; index <= (int)app.Documents.Count; index++)
                {
                    dynamic candidate = app.Documents.Item(index);
                    if (String.Equals(Convert.ToString(candidate.Name, CultureInfo.InvariantCulture), documentName, StringComparison.OrdinalIgnoreCase))
                    {
                        document = candidate;
                        break;
                    }
                }
                if (document == null)
                    throw new InvalidOperationException("Open Visio document not found: " + documentName);

                dynamic page = null;
                for (int index = 1; index <= (int)document.Pages.Count; index++)
                {
                    dynamic candidate = document.Pages.Item(index);
                    string name = Convert.ToString(candidate.Name, CultureInfo.InvariantCulture) ?? "";
                    string nameU = Convert.ToString(candidate.NameU, CultureInfo.InvariantCulture) ?? "";
                    if (String.Equals(name, pageName, StringComparison.OrdinalIgnoreCase) ||
                        String.Equals(nameU, pageName, StringComparison.OrdinalIgnoreCase))
                    {
                        page = candidate;
                        break;
                    }
                }
                if (page == null)
                    throw new InvalidOperationException("Visio page not found: " + pageName);

                foreach (Edge edge in edges)
                {
                    dynamic source = page.Shapes.ItemFromID(edge.SourceId);
                    dynamic target = page.Shapes.ItemFromID(edge.TargetId);
                    string sourceCellName = edge.Endpoint == "begin" ? "BeginX" : "EndX";
                    string targetCellName = "Connections.X" + edge.Row.ToString(CultureInfo.InvariantCulture);
                    source.CellsU(sourceCellName).GlueTo(target.CellsU(targetCellName));
                }

                File.WriteAllText(resultPath, "PASS\t" + edges.Count.ToString(CultureInfo.InvariantCulture), Encoding.UTF8);
                return 0;
            }
            catch (Exception ex)
            {
                try
                {
                    if (!String.IsNullOrWhiteSpace(resultPath))
                        File.WriteAllText(resultPath, "ERROR\t" + ex.ToString(), Encoding.UTF8);
                }
                catch { }
                return 1;
            }
        }
    }
}
