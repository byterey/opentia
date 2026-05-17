using FluentAssertions;
using SampleApp.Core.Utilities;

namespace SampleApp.Core.Tests.Utilities;

public class StringHelperTests
{
    [Theory]
    [InlineData("Hello World", 5, "Hello")]
    [InlineData("Hi",          10, "Hi")]
    [InlineData("",            5, "")]
    public void Truncate_ReturnsExpected(string input, int max, string expected)
    {
        StringHelper.Truncate(input, max).Should().Be(expected);
    }

    [Fact]
    public void Truncate_ZeroMaxLength_Throws()
    {
        Assert.Throws<ArgumentOutOfRangeException>(() => StringHelper.Truncate("hi", 0));
    }

    [Theory]
    [InlineData("hello world",  "Hello World")]
    [InlineData("HELLO WORLD",  "Hello World")]
    [InlineData("hello",        "Hello")]
    public void ToTitleCase_CapitalisesWords(string input, string expected)
    {
        StringHelper.ToTitleCase(input).Should().Be(expected);
    }

    [Theory]
    [InlineData("alice@example.com", true)]
    [InlineData("alice@example",     false)]
    [InlineData("aliceexample.com",  false)]
    [InlineData("",                  false)]
    public void IsValidEmail_CorrectlyValidates(string email, bool expected)
    {
        StringHelper.IsValidEmail(email).Should().Be(expected);
    }

    [Fact]
    public void MaskEmail_MasksLocalPart()
    {
        StringHelper.MaskEmail("alice@example.com").Should().Be("al***@example.com");
    }

    [Fact]
    public void MaskEmail_InvalidEmail_ReturnsSameString()
    {
        StringHelper.MaskEmail("notanemail").Should().Be("notanemail");
    }

    [Fact]
    public void RemoveWhitespace_RemovesAllSpacesAndTabs()
    {
        StringHelper.RemoveWhitespace("a b\tc").Should().Be("abc");
    }

    [Theory]
    [InlineData("Hello World", "hello-world")]
    [InlineData("C# Rules!",   "c-rules")]
    [InlineData("  ",           "")]
    public void Slugify_ProducesLowercaseHyphenated(string input, string expected)
    {
        StringHelper.Slugify(input).Should().Be(expected);
    }
}
