-- Pandoc Lua filter for arxiv-to-markdown
-- This filter handles special LaTeX conversions

-- Simplify math notation for token efficiency
function Math(elem)
  local text = elem.text
  
  -- Replace \boldsymbol with \mathbf
  text = text:gsub("\\boldsymbol{([^}]+)}", "\\mathbf{%1}")
  
  -- Replace \operatorname with plain text
  text = text:gsub("\\operatorname{([^}]+)}", "%1")
  
  -- Simplify \left( and \right)
  text = text:gsub("\\left%(", "(")
  text = text:gsub("\\right%)", ")")
  text = text:gsub("\\left%[", "[")
  text = text:gsub("\\right%]", "]")
  text = text:gsub("\\left%{", "{")
  text = text:gsub("\\right%}", "}")
  
  elem.text = text
  return elem
end

-- Handle figures (convert to placeholders since we're skipping images)
function Figure(elem)
  -- Get caption if available
  local caption = ""
  if elem.caption and elem.caption.long then
    caption = pandoc.utils.stringify(elem.caption.long)
  end
  
  return pandoc.Para(pandoc.Str("[Figure: " .. caption .. "]"))
end

-- Handle images (convert to placeholders)
function Image(elem)
  return pandoc.Str("[Figure: " .. elem.caption .. "]")
end

-- Remove LaTeX commands that don't translate well
function RawInline(elem)
  if elem.format == "tex" or elem.format == "latex" then
    -- Skip common non-essential commands
    if elem.text:match("^\\[a-zA-Z]+") then
      return {}
    end
  end
  return elem
end

-- Clean up reference links
function Link(elem)
  -- Ensure links are clean
  return elem
end
