function setupBedSolutionDatabase() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  ss.rename("Bed Solution — Manufacturing & Inventory DB");

  var headerBg = "#2E5434";
  var headerFg = "#E0A13B";
  var sampleBg = "#F4F7F4";

  var schema = [
    {
      name: "Materials",
      headers: ["Material_ID", "Material_Name", "Unit", "Reorder_Level"],
      widths: [130, 260, 100, 140],
      formats: ["@", "@", "@", "0.##"],
      sample: [
        ["MAT-001", "High-Density Orthopedic Foam (10cm)", "sheets", 5],
        ["MAT-002", "Bonnell Spring Unit (160x200)", "pcs", 10],
        ["MAT-003", "Quilted Jacquard Mattress Fabric", "meters", 15],
        ["MAT-004", "Seasoned Pine Wood Frame Timber", "meters", 20],
        ["MAT-005", "Industrial Upholstery Adhesive", "liters", 5]
      ]
    },
    {
      name: "Suppliers",
      headers: ["Supplier_ID", "Supplier_Name", "Contact_Person", "Phone", "Address", "TIN_No", "Notes"],
      widths: [130, 240, 180, 150, 220, 140, 220],
      formats: ["@", "@", "@", "@", "@", "@", "@"],
      sample: [
        ["SUP-001", "Addis Foam & Sponge Factory", "Ato Girma Bekele", "+251-911-234567", "Kality Industrial Zone, Addis Ababa", "0045128910", "Main high-density foam supplier"],
        ["SUP-002", "Merkato Textile & Upholstery Hub", "W/ro Selamawit Tadesse", "+251-912-987654", "Merkato Tana Bldg, Addis Ababa", "0078912345", "Jacquard & quilted mattress fabrics"]
      ]
    },
    {
      name: "Batches",
      headers: ["Batch_No", "Bed_Model", "Batch_Date", "Bed_Qty", "Status", "Notes"],
      widths: [160, 260, 130, 120, 140, 240],
      formats: ["@", "@", "yyyy-mm-dd", "0", "@", "@"],
      sample: [
        ["BATCH-261123-01", "Queen Orthopedic Mattress (160x200)", "2026-11-23", 1, "In Production", "1 Bed = 1 Batch Number"]
      ]
    },
    {
      name: "Purchases",
      headers: ["Purchase_ID", "Date", "Material_ID", "Supplier_ID", "Supplier_Name", "Qty", "Unit_Cost", "Payment_Type", "Invoice_No", "Notes"],
      widths: [150, 120, 130, 130, 220, 100, 130, 130, 130, 220],
      formats: ["@", "yyyy-mm-dd", "@", "@", "@", "0.##", "#,##0.00", "@", "@", "@"],
      sample: [
        ["PUR-001", "2026-11-23", "MAT-001", "SUP-001", '=IFERROR(VLOOKUP(D2, Suppliers!$A$2:$B$1000, 2, FALSE), "")', 25.5, 4200.00, "Cash", "INV-101", "Opening batch purchase"],
        ["PUR-002", "2026-11-23", "MAT-003", "SUP-002", '=IFERROR(VLOOKUP(D3, Suppliers!$A$2:$B$1000, 2, FALSE), "")', 60.0, 650.00, "Credit", "INV-102", "Roll delivery"]
      ]
    },
    {
      name: "Stock_Out",
      headers: ["Issue_ID", "Date", "Batch_No", "Material_ID", "Material_Name", "Qty", "Employee_ID", "Sub_Item", "Notes"],
      widths: [150, 120, 160, 130, 230, 100, 130, 200, 220],
      formats: ["@", "yyyy-mm-dd", "@", "@", "@", "0.##", "@", "@", "@"],
      sample: [
        ["ISS-001", "2026-11-23", "BATCH-261123-01", "MAT-001", '=IFERROR(VLOOKUP(D2, Materials!$A$2:$B$1000, 2, FALSE), "")', 0.5, "EMP-001", "Spring & Foam Core", "Decimal material issue"]
      ]
    },
    {
      name: "Opening_Stock",
      headers: ["Date", "Material_ID", "Material_Name", "Qty", "Unit_Cost"],
      widths: [120, 140, 230, 110, 140],
      formats: ["yyyy-mm-dd", "@", "@", "0.##", "#,##0.00"],
      sample: [
        ["2026-11-01", "MAT-005", '=IFERROR(VLOOKUP(B2, Materials!$A$2:$B$1000, 2, FALSE), "")', 4.5, 850.00]
      ]
    },
    {
      name: "Employees",
      headers: ["Employee_ID", "Employee_Name", "Role"],
      widths: [140, 220, 160],
      formats: ["@", "@", "@"],
      sample: [
        ["EMP-001", "Abebe Kebede", "Master Upholsterer"],
        ["EMP-002", "Dawit Tadesse", "Carpentry Lead"]
      ]
    },
    {
      name: "Supplier_Payments",
      headers: ["Date", "Supplier_ID", "Supplier_Name", "Amount"],
      widths: [130, 150, 220, 150],
      formats: ["yyyy-mm-dd", "@", "@", "#,##0.00"],
      sample: []
    },
    {
      name: "Opening_Payables",
      headers: ["Supplier_ID", "Supplier_Name", "Amount_Owed"],
      widths: [150, 220, 160],
      formats: ["@", "@", "#,##0.00"],
      sample: []
    }
  ];

  schema.forEach(function(tab) {
    var sheet = ss.getSheetByName(tab.name);
    if (!sheet) {
      sheet = ss.insertSheet(tab.name);
    } else {
      sheet.clear();
    }

    var headerRange = sheet.getRange(1, 1, 1, tab.headers.length);
    headerRange.setValues([tab.headers]);
    headerRange
      .setBackground(headerBg)
      .setFontColor(headerFg)
      .setFontWeight("bold")
      .setFontSize(11)
      .setHorizontalAlignment("center")
      .setVerticalAlignment("middle");
    sheet.setRowHeight(1, 32);
    sheet.setFrozenRows(1);

    for (var c = 0; c < tab.headers.length; c++) {
      sheet.setColumnWidth(c + 1, tab.widths[c]);
      sheet.getRange(2, c + 1, 999, 1).setNumberFormat(tab.formats[c]);
    }

    if (tab.sample && tab.sample.length > 0) {
      var sampleRange = sheet.getRange(2, 1, tab.sample.length, tab.headers.length);
      sampleRange.setValues(tab.sample);
      sampleRange.setBackground(sampleBg);
    }
  });

  // Auto-display Supplier_Name & Material_Name when ID is chosen in Google Sheets
  var purSheet = ss.getSheetByName("Purchases");
  var outSheet = ss.getSheetByName("Stock_Out");
  var opStkSheet = ss.getSheetByName("Opening_Stock");
  var paySheet = ss.getSheetByName("Supplier_Payments");
  var opPaySheet = ss.getSheetByName("Opening_Payables");

  for (var r = 2; r <= 200; r++) {
    purSheet.getRange(r, 5).setFormula('=IF(D' + r + '="","",IFERROR(VLOOKUP(D' + r + ',Suppliers!$A$2:$B$1000,2,FALSE),"Not Found"))');
    outSheet.getRange(r, 5).setFormula('=IF(D' + r + '="","",IFERROR(VLOOKUP(D' + r + ',Materials!$A$2:$B$1000,2,FALSE),"Not Found"))');
    opStkSheet.getRange(r, 3).setFormula('=IF(B' + r + '="","",IFERROR(VLOOKUP(B' + r + ',Materials!$A$2:$B$1000,2,FALSE),"Not Found"))');
    paySheet.getRange(r, 3).setFormula('=IF(B' + r + '="","",IFERROR(VLOOKUP(B' + r + ',Suppliers!$A$2:$B$1000,2,FALSE),"Not Found"))');
    opPaySheet.getRange(r, 2).setFormula('=IF(A' + r + '="","",IFERROR(VLOOKUP(A' + r + ',Suppliers!$A$2:$B$1000,2,FALSE),"Not Found"))');
  }

  // Dropdown validations
  purSheet.getRange("H2:H1000").setDataValidation(
    SpreadsheetApp.newDataValidation().requireValueInList(["Cash", "Credit"], true).build()
  );

  var batchSheet = ss.getSheetByName("Batches");
  batchSheet.getRange("E2:E1000").setDataValidation(
    SpreadsheetApp.newDataValidation().requireValueInList(["In Production", "Completed", "On Hold"], true).build()
  );

  outSheet.getRange("C2:C1000").setDataValidation(
    SpreadsheetApp.newDataValidation().requireValueInRange(batchSheet.getRange("A2:A1000"), true).build()
  );

  var matSheet = ss.getSheetByName("Materials");
  var matRule = SpreadsheetApp.newDataValidation().requireValueInRange(matSheet.getRange("A2:A1000"), true).build();
  outSheet.getRange("D2:D1000").setDataValidation(matRule);
  purSheet.getRange("C2:C1000").setDataValidation(matRule);
  opStkSheet.getRange("B2:B1000").setDataValidation(matRule);

  var supSheet = ss.getSheetByName("Suppliers");
  var supRule = SpreadsheetApp.newDataValidation().requireValueInRange(supSheet.getRange("A2:A1000"), true).build();
  purSheet.getRange("D2:D1000").setDataValidation(supRule);
  paySheet.getRange("B2:B1000").setDataValidation(supRule);
  opPaySheet.getRange("A2:A1000").setDataValidation(supRule);

  var empSheet = ss.getSheetByName("Employees");
  outSheet.getRange("G2:G1000").setDataValidation(
    SpreadsheetApp.newDataValidation().requireValueInRange(empSheet.getRange("A2:A1000"), true).build()
  );

  var defaultSheet = ss.getSheetByName("Sheet1");
  if (defaultSheet && ss.getSheets().length > 1) {
    ss.deleteSheet(defaultSheet);
  }

  SpreadsheetApp.getUi().alert("✅ Bed Solution DB ready: Full Supplier Info + Auto Name Lookup on ID selection!");
}
