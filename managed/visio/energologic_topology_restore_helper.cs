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

        private static bool FormulaReferencesTarget(
            string formula,
            dynamic target,
            int row,
            string axis)
        {
            string value = formula ?? "";
            string rowText = row.ToString(CultureInfo.InvariantCulture);
            string[] suffixes = new[] {
                "!Connections." + rowText + "." + axis,
                "!Connections." + axis + rowText
            };
            List<string> refs = new List<string>();
            refs.Add("Sheet." + Convert.ToInt32(target.ID, CultureInfo.InvariantCulture).ToString(CultureInfo.InvariantCulture));
            try
            {
                string name = Convert.ToString(target.Name, CultureInfo.InvariantCulture) ?? "";
                if (!String.IsNullOrWhiteSpace(name)) refs.Add(name);
            }
            catch { }
            try
            {
                string nameU = Convert.ToString(target.NameU, CultureInfo.InvariantCulture) ?? "";
                if (!String.IsNullOrWhiteSpace(nameU)) refs.Add(nameU);
            }
            catch { }

            foreach (string targetRef in refs)
            {
                foreach (string suffix in suffixes)
                {
                    string direct = targetRef + suffix;
                    string quoted = "'" + targetRef + "'" + suffix;
                    if (value.IndexOf(direct, StringComparison.OrdinalIgnoreCase) >= 0 ||
                        value.IndexOf(quoted, StringComparison.OrdinalIgnoreCase) >= 0)
                        return true;
                }
            }
            return false;
        }

        private static bool IsGlueCorrect(dynamic page, Edge edge)
        {
            try
            {
                dynamic source = page.Shapes.ItemFromID(edge.SourceId);
                dynamic target = page.Shapes.ItemFromID(edge.TargetId);
                string xName = edge.Endpoint == "begin" ? "BeginX" : "EndX";
                string yName = edge.Endpoint == "begin" ? "BeginY" : "EndY";
                string xFormula = Convert.ToString(source.CellsU(xName).FormulaU, CultureInfo.InvariantCulture) ?? "";
                string yFormula = Convert.ToString(source.CellsU(yName).FormulaU, CultureInfo.InvariantCulture) ?? "";

                // A valid 1-D Glue must bind BOTH coordinates to the same connection
                // point. This deliberately rejects VTD's half-Glue state where X is
                // numeric but Y still contains PAR(PNT(...)).
                return FormulaReferencesTarget(xFormula, target, edge.Row, "X") &&
                       FormulaReferencesTarget(yFormula, target, edge.Row, "Y");
            }
            catch { return false; }
        }

        private static void GlueAndVerify(dynamic page, Edge edge)
        {
            dynamic source = page.Shapes.ItemFromID(edge.SourceId);
            dynamic target = page.Shapes.ItemFromID(edge.TargetId);
            string sourceCellName = edge.Endpoint == "begin" ? "BeginX" : "EndX";
            string targetCellName = "Connections.X" + edge.Row.ToString(CultureInfo.InvariantCulture);
            source.CellsU(sourceCellName).GlueTo(target.CellsU(targetCellName));
            if (!IsGlueCorrect(page, edge))
                throw new InvalidOperationException(
                    String.Format(
                        CultureInfo.InvariantCulture,
                        "External GlueTo formula verification failed: source {0} {1}; target {2}/{3}",
                        edge.SourceId,
                        edge.Endpoint,
                        edge.TargetId,
                        edge.Row
                    )
                );
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

                int repaired = 0;
                int verified = 0;
                foreach (Edge edge in edges)
                {
                    try
                    {
                        dynamic source = page.Shapes.ItemFromID(edge.SourceId);
                        if (!IsGlueCorrect(page, edge))
                        {
                            GlueAndVerify(page, edge);
                            repaired++;
                        }
                        else
                        {
                            // Re-read through the external COM process so PASS always
                            // means the actual live Visio topology matched the plan.
                            if (!IsGlueCorrect(page, edge))
                                throw new InvalidOperationException("External Glue verification was not stable");
                        }
                        verified++;
                    }
                    catch (Exception edgeError)
                    {
                        throw new InvalidOperationException(
                            String.Format(CultureInfo.InvariantCulture,
                                "External Glue verification failed: source {0} {1}; target {2}/{3}",
                                edge.SourceId, edge.Endpoint, edge.TargetId, edge.Row),
                            edgeError);
                    }
                }

                File.WriteAllText(
                    resultPath,
                    "PASS\t" +
                    repaired.ToString(CultureInfo.InvariantCulture) + "\t" +
                    verified.ToString(CultureInfo.InvariantCulture),
                    Encoding.UTF8
                );
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
